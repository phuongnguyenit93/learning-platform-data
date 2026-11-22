# `Parameter.isNamePresent()` và tên tổng hợp `arg0`, `arg1` trong Java Reflection

## 1. Cùng một method, vì sao Reflection lúc thấy tên thật, lúc chỉ thấy `arg0`?

Một method có thể được khai báo như sau:

~~~java
void send(String recipient, int attempts) {
    // ...
}
~~~

Trong mã nguồn, tham số có tên `recipient` và `attempts`. Tuy nhiên, **tên tham số trong mã nguồn không mặc nhiên được ghi vào bytecode dưới dạng metadata Reflection có thể truy cập**. Khi dùng `Method.getParameters()` để lấy các đối tượng `java.lang.reflect.Parameter`, chúng ta có hai khả năng:

- Class file có metadata tên tham số phù hợp: `Parameter.getName()` trả `recipient`, `attempts` và `Parameter.isNamePresent()` trả `true`.
- Class file không có metadata tên tham số: Java Reflection tạo tên thay thế theo dạng **`arg0`, `arg1`, …**, và `Parameter.isNamePresent()` trả `false`.

Điểm then chốt: **`getName()` vẫn trả một chuỗi kể cả khi tên thật không có trong class file**. Vì vậy chỉ gọi `getName()` rồi thấy `arg0` không chứng minh tác giả đã đặt tham số tên `arg0`, và không phải một cơ chế phục hồi tên gốc từ bytecode.

Hai nhóm thông tin độc lập:

1. **Thông tin chữ ký của executable:** số lượng tham số, loại tham số, thứ tự; JVM cần chúng để kiểm tra chữ ký và thực hiện lời gọi.
2. **Thông tin tên nguồn của tham số:** tên như `recipient` hay `attempts` để hỗ trợ tooling, framework, binding; Java Reflection chỉ biết chúng khi metadata được phát hành và còn nguyên vẹn.

`isNamePresent()` là cách chính thức để phân biệt hai tình huống trên.

## 2. API trực tiếp phục vụ quyết định tên tham số

`Method` và `Constructor<?>` cùng kế thừa `Executable`. `getParameters()` trả các `Parameter` theo thứ tự của executable; `getParameterCount()` và `getParameterTypes()` vẫn hoạt động khi không có metadata tên.

| API | Câu hỏi trả lời |
| --- | --- |
| `Parameter.getName()` | Class file cung cấp tên nào, hoặc Reflection đã tạo tên thay thế `argN` nào? |
| `Parameter.isNamePresent()` | Riêng tham số này có tên trong metadata `MethodParameters` không? |
| `Parameter.getDeclaringExecutable()` | Method/constructor nào khai báo tham số này? |
| `Parameter.getType()` | Kiểu runtime sau type erasure là gì? |

Vì tên không tham gia chữ ký overload, hãy tra method bằng tên method và danh sách `Class<?>`, sau đó kiểm tra **từng** `Parameter.isNamePresent()` nếu cần tên để binding. `Parameter` mô tả khai báo, không lưu giá trị của một lần gọi thực tế.

## 3. Thực hành Java 17: cùng source, hai kết quả

Tạo đúng một file `ParameterNamesDemo.java`:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Executable;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterNamesDemo {
    public static void main(String[] args) throws Exception {
        Class<Submission> type = Submission.class;

        Constructor<Submission> ctor =
                type.getDeclaredConstructor(String.class, long.class);
        Method method =
                type.getDeclaredMethod("send", String.class, int.class);

        inspect("constructor", ctor);
        inspect("method", method);
    }

    private static void inspect(String label, Executable executable) {
        System.out.println(label + ": " + executable.getParameterCount());

        for (Parameter p : executable.getParameters()) {
            System.out.println("  " + p.getName()
                    + " | present=" + p.isNamePresent()
                    + " | type=" + p.getType().getSimpleName());
        }
    }
}

class Submission {
    Submission(String label, long createdAt) {
    }

    void send(String recipient, int attempts) {
    }
}
~~~

### Lần 1 — Biên dịch mặc định, không giữ tên tham số

Trong thư mục chứa file, chạy:

~~~bash
javac --release 17 ParameterNamesDemo.java
java ParameterNamesDemo
~~~

Kết quả:

~~~text
constructor: 2
  arg0 | present=false | type=String
  arg1 | present=false | type=long
method: 2
  arg0 | present=false | type=String
  arg1 | present=false | type=int
~~~

Cả constructor và method đều có hai tham số với đúng **kiểu** và đúng **thứ tự**, nhưng tên nguồn không được lưu bằng metadata tên tham số được Reflection nhận biết. `getName()` do đó tạo ra `arg0`, `arg1` và `isNamePresent()` trả `false`.

### Lần 2 — Biên dịch lại cùng source với `-parameters`

Chạy tiếp (giữ nguyên file `.java`):

~~~bash
javac --release 17 -parameters ParameterNamesDemo.java
java ParameterNamesDemo
~~~

Kết quả:

~~~text
constructor: 2
  label | present=true | type=String
  createdAt | present=true | type=long
method: 2
  recipient | present=true | type=String
  attempts | present=true | type=int
~~~

Chỉ khác lựa chọn biên dịch, `getName()` giờ lấy được tên khai báo, `isNamePresent()` trả `true` cho từng tham số. Method và constructor vẫn có chữ ký Java, số lượng và kiểu tham số như trước.

**Thí nghiệm này đã được xác minh** với Java Compiler qua API `javax.tools.JavaCompiler` ở chế độ `--release 17`, so sánh hai lượt có/không có `-parameters`. Khác biệt không cần sửa logic method hay constructor.

### Phân tích kỹ hơn

- `Submission(String label, long createdAt)` là constructor package-private, nhưng `getDeclaredConstructor(String.class, long.class)` vẫn tìm thấy metadata.
- `send(String recipient, int attempts)` cũng không cần là method public: `getDeclaredMethod(String, Class<?>...)` lấy khai báo trong class tương ứng.
- Việc đọc tên/type qua `getParameters()` không đòi gọi constructor/method; đây là metadata. Nếu sau đó dùng `newInstance` hoặc `invoke` mới phát sinh các access check riêng.
- Ví dụ chỉ sử dụng **top-level class** thông thường và tham số được khai báo tường minh. Với constructor của enum, non-static inner class hay những hình thức compiler-generated khác, có thể có tham số implicit/synthetic cần phân tích riêng.

## 4. Chẩn đoán chính xác tên tổng hợp

`javac -parameters` yêu cầu ghi tên tham số trong thuộc tính `MethodParameters` của class file. `-g` có thể tạo `LocalVariableTable` cho debugger, nhưng Core Reflection không dùng bảng debug đó để quyết định `isNamePresent()`. Kiểm tra class file đang thực thi bằng `javap -v -p` và tìm `MethodParameters` tại đúng method/constructor.

**Không nhận diện tên tổng hợp bằng regex.** Source hoàn toàn có thể cố ý khai báo tham số tên `arg0`; khi biên dịch với `-parameters`, `getName()` vẫn là `arg0` nhưng `isNamePresent()` là `true`. Ngược lại, thiếu tên metadata thì `argN` chỉ là nhãn Reflection tự tạo.

## 5. Kiểm tra bản build thực sự được nạp

Chạy thí nghiệm ở mục 3 trong hai thư mục output tách biệt (ví dụ `plain/` và `named/`) để tránh đọc lại `.class` cũ. Với `named/`, dùng `javac --release 17 -parameters -d named ParameterNamesDemo.java`; với `plain/`, bỏ `-parameters`. Chọn classpath tương ứng khi chạy rồi so `getName()` và `isNamePresent()`.

Trong ứng dụng nhiều module, chỉ những class **đã được chính compiler/build pipeline phát hành metadata** mới có tên. Nếu thư viện JAR, CI, obfuscator hoặc bytecode transformer xử lý riêng, cần kiểm tra artifact cuối. Cấu hình Maven/Gradle chi tiết và vai trò `-g` đã được trình bày ở bài **Tên tham số và tùy chọn biên dịch `-parameters`**; ở đây trọng tâm là kiểm tra kết quả trên từng `Parameter`.

## 6. Tên tổng hợp `arg0`, `arg1` có dùng làm tên nghiệp vụ được không?

Không nên. Khi metadata tên không có, `getName()` trả tên theo thứ tự **`arg0`, `arg1`, …** cho các tham số; đó là cơ chế dự phòng để Reflection vẫn có chuỗi tên, **không phải tên khai báo đáng tin cậy từ source**.

Ví dụ một framework ánh xạ request JSON:

~~~java
void createUser(String email, int age)
~~~

Nếu framework định bind tham số theo tên `email` và `age` nhưng class file không có tên, nó có thể chỉ quan sát `arg0` và `arg1`. Nếu framework không có cơ chế định danh thay thế, mapping có thể thất bại hoặc gây nhầm lẫn. Framework có thể dùng annotation như `@RequestParam("email")`, `@JsonProperty("age")`, hoặc metadata riêng; hành vi thực tế phụ thuộc framework.

**Cách đúng:** nếu cần tên tham số nguồn, chỉ tin `getName()` khi `isNamePresent()` là true (và metadata đúng với artifact mong muốn). Nếu false, xử lý như tình huống **thiếu metadata**: yêu cầu cấu hình `-parameters`, dùng annotation đặt tên tường minh, hoặc sử dụng contract nhận diện tham số khác. Không tự ép `arg0` thành tên business.

Đây cũng là lý do một API/framework có thể chạy bình thường trong IDE nhưng lỗi ở bản đóng gói: cấu hình compiler hay bước tối ưu bytecode của hai môi trường có thể khác nhau.

## 7. Ngoại lệ và trường hợp ít hiển nhiên

### a) Constructor có tham số ngầm/nhân tạo

Một `non-static inner class` có thể mang tham số ẩn trỏ về instance outer class, dù người đọc source chỉ thấy constructor khai báo một vài tham số. Constructor của `enum` cũng có tham số do compiler/runtime bổ sung; các executable synthetic/bridge có thể xuất hiện trong bytecode.

Đừng mặc định tham số index 0 trong Reflection luôn tương ứng với **tham số đầu tiên người viết nhìn thấy trong mã nguồn**. Khi nghi ngờ, kiểm tra `getParameterTypes()`, `getParameters()`, `Parameter.isImplicit()`, `Parameter.isSynthetic()` và metadata của class file. Giá trị các flag phụ thuộc compiler/bytecode, nên không tự suy diễn dựa vào tên `arg0`.

### b) `isNamePresent()` là kiểm tra trên từng `Parameter`

Chữ ký API là `parameter.isNamePresent()`, không phải thuộc tính boolean duy nhất trên toàn class. Khi xử lý tổng quát, kiểm tra **mỗi tham số** của executable. Tránh mặc định rằng nếu một tham số có tên thì tất cả sẽ có tên, nhất là khi làm việc với class file từ compiler, code generator hoặc công cụ biến đổi bytecode khác nhau.

~~~java
for (Parameter p : executable.getParameters()) {
    if (p.isNamePresent()) {
        System.out.println("Known name: " + p.getName());
    } else {
        System.out.println("Unnamed parameter, type: " + p.getType());
    }
}
~~~

Đây là mảnh code dùng lại `executable` trong phương thức `inspect` của bài, không phải chương trình độc lập.

### c) Record, enum, lambda và code compiler tạo

Với `record`, canonical constructor và thành phần record có cơ chế metadata đặc thù; một số compiler/JDK có thể lưu tên cho các thành phần đặc biệt ngay cả khi cách build thông thường không dùng `-parameters`. Lambda, bridge method, enum constructor và synthetic executable cũng có thể không phản ánh tên nguồn theo cách bạn kỳ vọng.

Vì vậy kết luận chính xác là: **đối với method/constructor thông thường như bài thực hành, bỏ `-parameters` dẫn tới `argN` và `isNamePresent=false`; với executable đặc biệt, phải kiểm tra metadata thực tế của class file**. Không tuyên bố mọi đối tượng `Parameter` ở mọi class file sẽ đều có `isNamePresent=false` nếu không truyền cờ.

### d) Annotation và kiểu tham số không biến mất khi tên biến mất

Dù `isNamePresent=false`, Java Reflection vẫn có thể biết `getType()`, số lượng tham số và annotation runtime (nếu annotation có retention thích hợp). Ví dụ annotation gắn tên nghiệp vụ tường minh là một đường metadata độc lập với `-parameters`. `getParameterizedType()` còn có thể cung cấp thông tin generic nếu metadata chữ ký được giữ.

Đừng nhầm “không thấy **tên**” với “không còn **tham số**”. Một method có hai tham số tiếp tục có hai `Parameter` được xây dựng từ descriptor/chữ ký phù hợp.

## 8. Lỗi thường gặp khi dùng `isNamePresent()`

- **Dùng `getName() != null` để xác nhận tên source:** tên tổng hợp cũng không null; phải kiểm tra `isNamePresent()`.
- **Dùng `startsWith("arg")` để phát hiện tên giả:** source có thể khai báo chính tên `arg0`; kiểm tra boolean từ API.
- **Kiểm tra một tham số rồi tin cả method:** xét từng phần tử `Parameter[]` riêng.
- **Cho rằng thiếu tên là thiếu kiểu/annotation:** descriptor, generic signature và runtime annotations là các nguồn metadata riêng.
- **Dùng tên reflection làm public key ngay khi `isNamePresent=true`:** tên tồn tại trong artifact nhưng có thể đổi bởi refactor hoặc quá trình build; contract bên ngoài cần quy tắc riêng.

## 9. Câu hỏi tự kiểm tra

**Câu 1:** `getName()` trả `arg0`. Có chắc tên trong source là `arg0` không? **Không.** Nếu `isNamePresent=false` thì đây là tên thay thế do Reflection cung cấp.

**Câu 2:** Một method có hai tham số nhưng cả hai `isNamePresent=false`. JVM có mất kiểu tham số không? **Không.** `getParameterTypes` và descriptor vẫn mô tả kiểu, số lượng và thứ tự.

**Câu 3:** Cờ nào lưu tên tham số cho Java Reflection: `-g` hay `-parameters`? **`-parameters`.** Thông tin debug của `-g` không thay thế được metadata này.

**Câu 4:** Có thể dùng tên tham số để tìm một overloaded method qua `getDeclaredMethod` không? **Không.** Tra cứu dùng **tên method** và danh sách **kiểu tham số**, không dùng tên từng parameter.

**Câu 5:** Tại sao một executable compiler-generated có thể cho metadata khác ví dụ trên? **Vì compiler có thể thêm tham số implicit/synthetic hoặc phát hành metadata đặc biệt.** Cần xem `Parameter.isImplicit`, `isSynthetic` và class file thực tế.

**Câu 6:** Nếu framework bắt buộc biết tên source nhưng `isNamePresent=false`, nên làm gì? **Bật `-parameters` cho build cần thiết, kiểm tra artifact cuối, hoặc dùng annotation/contract nêu tên tường minh.**

**Ghi nhớ:** `Parameter.getName()` **luôn cung cấp tên để hiển thị**, nhưng `Parameter.isNamePresent()` mới giúp phân biệt **tên có metadata thực** với **tên tổng hợp `arg0`, `arg1`**. Để framework dựa vào tên tham số hoạt động ổn định, phải quản lý compiler option và chất lượng class file cuối cùng.
