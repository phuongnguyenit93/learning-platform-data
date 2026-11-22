# Lưu tên tham số bằng `-parameters` và giới hạn của thông tin này

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao tên tham số `left`, `right` trong mã nguồn Java không mặc nhiên xuất hiện khi đọc bằng Reflection lúc chạy.
- Dùng `javac -parameters` để lưu tên formal parameters của **method** và **constructor** vào class file, rồi xác minh bằng `java.lang.reflect.Parameter` và `javap`.
- Phân biệt metadata `MethodParameters` với debug information (`LocalVariableTable`, `-g`), kiểu generic, annotation và tên local variable.
- Bật tùy chọn compiler trong dự án Gradle/Maven và kiểm tra class file thực sự được ứng dụng sử dụng.
- Nhận diện trường hợp metadata thiếu, bị biến đổi hoặc có tên khác giữa interface/implementation; xử lý an toàn khi một framework dựa vào tên tham số để binding.

Đây là bài về **cấu hình biên dịch và metadata tên tham số**, không phải hướng dẫn bao quát mọi kỹ thuật Reflection.

## 1. Tại sao Java có thể quên tên tham số?

Xét đoạn mã thuộc một lớp Java:

~~~java
public static int multiply(int left, int right) {
    return left * right;
}
~~~

Khi đọc source, bạn thấy hai tên `left` và `right`. Nhưng để gọi phương thức ở mức JVM, tên phương thức, kiểu và thứ tự tham số mới là những thông tin quan trọng để xác định method descriptor. Tên tham số người viết chọn **không cần thiết** để máy ảo thực thi phép nhân.

Vì thế, khi biên dịch thông thường, một file `.class` có thể giữ cấu trúc phương thức và các kiểu `int` mà không có metadata phản chiếu hai tên ở source. Java Reflection vẫn lấy được một mảng hai đối tượng `Parameter`, nhưng `getName()` thường tạo tên thay thế:

~~~text
arg0
arg1
~~~

Các tên `arg0` và `arg1` là tên tổng hợp dựa trên chỉ số tham số; chúng không chứng minh source đã khai báo hai tên này.

Từ Java 8, `javac` có tùy chọn `-parameters` để giữ **tên formal parameters** trong class file. Nó đặc biệt hữu ích với thư viện/framework đọc signature của method/constructor lúc chạy, ví dụ để ánh xạ tên đầu vào đến tham số.

Luồng xử lý:

~~~text
Source:
  int multiply(int left, int right)
                  |
                  | javac -parameters
                  v
Class file:
  method descriptor: (II)I
  MethodParameters: left, right
                  |
                  | JVM nạp class / Java Reflection
                  v
  Method.getParameters()
                  |
                  +--> getName(): "left", "right"
                  +--> isNamePresent(): true, true
~~~

`(II)I` biểu diễn hai tham số `int` và một giá trị trả về `int` trong JVM descriptor. Những tên `left`, `right` là metadata bổ sung; chúng không biến đổi descriptor này.

## 2. `-parameters` thực sự ghi gì?

Trong những class file mà `javac` sinh với:

~~~bash
javac -parameters Example.java
~~~

compiler ghi metadata **`MethodParameters`** phù hợp cho các khai báo method/constructor. Thuộc tính này có thể chứa tên và cờ của từng tham số, gồm các trường hợp đặc biệt như `synthetic` hoặc `mandated`.

API Java tiêu chuẩn để đọc:

| API | Vai trò |
| --- | --- |
| `Method.getParameters()` | Trả đối tượng `Parameter[]` cho method được phản chiếu |
| `Constructor.getParameters()` | Trả `Parameter[]` cho constructor được phản chiếu |
| `Parameter.getName()` | Trả tên trong class-file metadata; nếu không có tên thực, trả tên thay thế như `arg0` |
| `Parameter.isNamePresent()` | Xác nhận metadata tên tham số thực có được lưu hay không |
| `Parameter.getType()` | Trả kiểu `Class<?>` của tham số, không phụ thuộc cờ lưu tên |
| `Parameter.getParameterizedType()` | Đọc thông tin kiểu tham số, bao gồm generic nếu metadata generic phù hợp tồn tại |
| `Parameter.isImplicit()` / `isSynthetic()` | Giúp nhận diện một số tham số do quy tắc ngôn ngữ hoặc compiler tạo |

**Điểm then chốt:** tên trong source chưa phải lời cam kết tồn tại tại runtime. Ngược lại, sự tồn tại của `MethodParameters` cũng không có nghĩa metadata ấy đủ để giải thích mọi ngữ nghĩa của method.

### 2.1 Tại sao không kiểm tra bằng tên `arg0`?

Không nên viết logic kiểu “nếu `getName()` bắt đầu bằng `arg` thì chắc chắn metadata thiếu”. Người viết source hoàn toàn có thể đặt tên thật là `arg0`. Khi đã biên dịch với cờ, `getName()` vẫn trả `arg0` và `isNamePresent()` trả `true`.

Hãy luôn dùng `isNamePresent()` nếu hệ thống yêu cầu tên chính xác đã khai báo. Một thư viện hỗ trợ tùy chọn cũng có thể đưa ra fallback tường minh khi metadata không có.

### 2.2 Không phải thông tin về lời gọi cụ thể

Giả sử mã khai báo:

~~~java
public void send(String recipient, int attempts)
~~~

thì tên được lưu có thể là `recipient` và `attempts`. Nó **không ghi giá trị cụ thể** của bất kỳ lời gọi nào, ví dụ `"An"` hoặc `3`. Đối tượng `Parameter` thuộc về **khai báo phương thức**; nó không phải cửa sổ nhìn vào một stack frame đang thực thi.

Tương tự, `-parameters` không cho biết tham số có nên null hay không, không thêm validation, không lưu mô tả JavaDoc và không biến Java thành ngôn ngữ gọi hàm bằng named arguments.

## 3. Thực hành đối chiếu bằng Java 17+

Bạn cần JDK 17+ và terminal; không cần IDE hay framework. Kiểm tra các lệnh:

~~~bash
java -version
javac -version
~~~

Kết quả sẽ phụ thuộc vào JDK/vendor được cài trên máy. Đảm bảo `java` và `javac` trỏ tới những phiên bản phù hợp; trên Windows có thể dùng `Get-Command java` và `Get-Command javac` trong PowerShell, trên Bash/Zsh dùng `command -v`.

### 3.1 Tạo ví dụ Reflection hoàn chỉnh

Tạo file **`src/ParameterNamesDemo.java`** (mã hóa UTF-8):

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterNamesDemo {
    public static int multiply(int left, int right) {
        return left * right;
    }

    public static void main(String[] args) throws Exception {
        Method method = ParameterNamesDemo.class
                .getDeclaredMethod("multiply", int.class, int.class);

        for (Parameter parameter : method.getParameters()) {
            System.out.println(parameter.getName()
                    + " | present=" + parameter.isNamePresent()
                    + " | type=" + parameter.getType().getSimpleName());
        }

        System.out.println("Tich = " + multiply(6, 7));
    }
}
~~~

Đây là chương trình độc lập. `getDeclaredMethod` tìm method bằng **tên và kiểu tham số**, không tra cứu tên `left` hay `right`. Vòng lặp đọc metadata cho từng `Parameter`, sau đó chương trình chạy logic nhân hai số.

### 3.2 Tách thư mục biên dịch để không chạy nhầm class

Đứng trong thư mục project có `src/ParameterNamesDemo.java`. Tạo hai thư mục output:

**PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out/without, out/with | Out-Null
~~~

**Bash/Zsh:**

~~~bash
mkdir -p out/without out/with
~~~

Mục đích của việc dùng hai output là giữ cùng lúc **hai bản class được build bằng hai cấu hình khác nhau**. Nếu chỉ build cả hai lần vào một thư mục, bạn dễ nhầm do bản sau đã thay thế bản trước.

### 3.3 Biên dịch không có `-parameters`

~~~bash
javac -encoding UTF-8 -d out/without src/ParameterNamesDemo.java
java -cp out/without ParameterNamesDemo
~~~

Khi `javac` biên dịch mặc định không lưu tên tham số qua `MethodParameters`, stdout của chương trình:

~~~text
arg0 | present=false | type=int
arg1 | present=false | type=int
Tich = 42
~~~

Compiler thông thường không in dòng nào khi thành công. Ba dòng trên do chương trình Java in lúc **chạy**, không phải do `javac` báo.

### 3.4 Biên dịch có `-parameters`

~~~bash
javac -parameters -encoding UTF-8 -d out/with src/ParameterNamesDemo.java
java -cp out/with ParameterNamesDemo
~~~

Stdout:

~~~text
left | present=true | type=int
right | present=true | type=int
Tich = 42
~~~

Hai bản chương trình đều trả tích `42`; chỉ metadata phản chiếu tên tham số khác nhau. `-parameters` không yêu cầu lập trình viên đổi chữ ký method, không thay cơ chế Java gọi `multiply(6, 7)` và không khiến JVM tạo thêm một đối số.

Bước này nên được tự kiểm tra bằng cách lần lượt chạy đúng `-cp out/without` và `-cp out/with`. Nếu cả hai bản cùng ra tên thật, hãy kiểm tra bạn có vô tình chạy cùng artifact hoặc có công cụ khác tác động tới class file hay không.

### 3.5 Quan sát class file với `javap`

`javap` là công cụ đi kèm JDK dùng để đọc thông tin class file:

~~~bash
javap -v -p -classpath out/without ParameterNamesDemo
javap -v -p -classpath out/with ParameterNamesDemo
~~~

Tìm phần mô tả method `multiply`. Ở bản build với `-parameters`, `javap -v` sẽ thể hiện một phần có ý nghĩa như:

~~~text
MethodParameters:
  Name                           Flags
  left
  right
~~~

`javap -v` còn in constant pool, bytecode, offset và những thông tin khác; trích đoạn trên chỉ tập trung vào thuộc tính liên quan. Kết quả đầy đủ có thể khác giữa các bản JDK.

Với bản thiếu cờ, phần `MethodParameters` của `multiply` có thể không tồn tại. **Không nên kiểm tra chỉ bằng việc tìm chuỗi `left` trong toàn bộ file class**: một số tên có thể xuất hiện trong các thuộc tính debug khác. Việc người đọc tìm thấy chuỗi trong file class không bảo đảm `Parameter.getName()` đọc được tên đó.

### 3.6 Cấu trúc thư mục sau khi build

~~~text
project/
├── src/
│   └── ParameterNamesDemo.java
└── out/
    ├── without/
    │   └── ParameterNamesDemo.class
    └── with/
        └── ParameterNamesDemo.class
~~~

`java -cp out/with ParameterNamesDemo` chọn bản `.class` có metadata. `java -cp out/without ParameterNamesDemo` chọn bản thiếu metadata. Nếu sử dụng sai classpath, lời gọi phản chiếu phản ánh class thực sự được JVM nạp, không phản ánh ý định của người build.

### 3.7 Kết quả biên dịch thành công không đủ để chứng minh tên được lưu

Dù `javac` trả exit code 0, vẫn có thể có một cấu hình không truyền `-parameters`. Khi yêu cầu nghiệp vụ cần tên tham số, bài kiểm tra nên là:

1. Xác định file `.class` hoặc JAR **thực sự chạy**.
2. Kiểm tra `MethodParameters` bằng `javap -v`.
3. Chạy code Reflection kiểm tra `Parameter.isNamePresent()`.
4. Thử một method/constructor thực tế mà framework đang phân tích.

Chỉ xem log “BUILD SUCCESSFUL” không trả lời được câu hỏi metadata đã tồn tại hay chưa.

## 4. Constructor cũng nhận metadata tên tham số

`-parameters` không chỉ áp dụng với method. Tạo file **`src/ConstructorNamesDemo.java`**:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public class ConstructorNamesDemo {
    private final String title;
    private final int count;

    public ConstructorNamesDemo(String title, int count) {
        this.title = title;
        this.count = count;
    }

    public static void main(String[] args) throws Exception {
        Constructor<ConstructorNamesDemo> constructor =
                ConstructorNamesDemo.class.getConstructor(String.class, int.class);

        for (Parameter parameter : constructor.getParameters()) {
            System.out.println(parameter.getName()
                    + " | present=" + parameter.isNamePresent());
        }

        ConstructorNamesDemo item = constructor.newInstance("Sách", 3);
        System.out.println(item.title + ": " + item.count);
    }
}
~~~

Biên dịch và chạy có cờ:

~~~bash
javac -parameters -encoding UTF-8 -d out/with src/ConstructorNamesDemo.java
java -cp out/with ConstructorNamesDemo
~~~

Stdout:

~~~text
title | present=true
count | present=true
Sách: 3
~~~

Biên dịch và chạy không có cờ:

~~~bash
javac -encoding UTF-8 -d out/without src/ConstructorNamesDemo.java
java -cp out/without ConstructorNamesDemo
~~~

Stdout:

~~~text
arg0 | present=false
arg1 | present=false
Sách: 3
~~~

Việc khởi tạo `ConstructorNamesDemo` diễn ra theo **thứ tự tham số và mã trong constructor**. Tên tham số được lưu không phải thứ làm phép gán `this.title = title` hoạt động.

### Khi có constructor “ẩn” hoặc tham số compiler-generated

Một số loại class có thể khiến compiler tạo thêm tham số trong bytecode mà người đọc source không trực tiếp thấy, như inner class không phải `static` hoặc enum. Khi đó, các phần tử trong `Constructor.getParameters()` có thể khác với danh sách bạn tưởng tượng từ source. Những cờ `isImplicit()` hoặc `isSynthetic()`, cùng thông tin kiểu và class file thực tế, giúp phân tích các trường hợp này.

Đừng mặc định mọi constructor đều có đúng số tham số như chữ ký nhìn thấy trong source hoặc mọi tham số phản chiếu đều là tham số do tác giả tự viết. Với mapper hoặc dependency-injection container, trường hợp constructor do compiler bổ sung có thể ảnh hưởng logic chọn constructor hoặc binding.

## 5. Không được nhầm `-parameters` với `-g`

`javac` có các tùy chọn debug information khác nhau. Tên formal parameter ở `MethodParameters` và tên biến trong debugger được lưu theo **các cơ chế khác nhau**.

| Cơ chế | Metadata liên quan | Công dụng | Đọc tên qua `Parameter.getName()`? |
| --- | --- | --- | --- |
| `-parameters` | `MethodParameters` | Lưu tên formal parameters của executable | Có, nếu metadata tồn tại |
| `-g` | Debug attributes, gồm source, line và biến cục bộ khi áp dụng | Debugger và phân tích bytecode | Không đủ bảo đảm |
| `-g:vars` | Thông tin local variables, thường `LocalVariableTable` | Đọc tên biến trong công cụ hỗ trợ debug | Không thay thế `MethodParameters` |
| `-g:none` | Không sinh debug information theo lựa chọn đó | Giảm dữ liệu debug | Vẫn có thể lưu `MethodParameters` bằng `-parameters` |
| Annotation runtime | `RuntimeVisibleAnnotations` hoặc metadata annotation phù hợp | Tham số/phương thức có annotation | Không tự lưu tên formal parameter |
| Generic signature | `Signature` khi cần | Giúp Reflection đọc generic type | Không liên quan trực tiếp đến tên |

Ví dụ build **vừa lưu tên, vừa không sinh debug information**:

~~~bash
javac -parameters -g:none -encoding UTF-8 -d out/with src/ParameterNamesDemo.java
java -cp out/with ParameterNamesDemo
~~~

Stdout về tên vẫn là:

~~~text
left | present=true | type=int
right | present=true | type=int
Tich = 42
~~~

Trong chiều ngược lại, thử:

~~~bash
javac -g -encoding UTF-8 -d out/without src/ParameterNamesDemo.java
java -cp out/without ParameterNamesDemo
~~~

`-g` không bảo đảm `isNamePresent()` thành `true`. Công cụ đọc `LocalVariableTable` có thể suy ra một số tên khi bytecode phù hợp, nhưng **Java Reflection chuẩn không dùng `-g` như cách thay thế cho `-parameters`**.

### Formal parameter không phải local variable bất kỳ

Xét đoạn mã thuộc một lớp:

~~~java
static int square(int value) {
    int result = value * value;
    return result;
}
~~~

`value` là formal parameter, `result` là biến cục bộ. Cờ `-parameters` hướng tới tên `value` của method; nó không cung cấp API Reflection để liệt kê tất cả local variables cùng tên `result`. Nếu cần xem tên biến ở debugger, đó là chủ đề của debug metadata.

### Annotation trên tham số cũng là dữ liệu độc lập

Ví dụ chữ ký minh họa:

~~~java
void update(@Deprecated String identifier) {
    // Đoạn này được đặt trong một lớp, không phải chương trình độc lập.
}
~~~

Annotation không tự khiến `identifier` có mặt trong `MethodParameters`. Việc annotation xuất hiện ở runtime phụ thuộc `@Retention` của loại annotation và cấu hình compiler; tên tham số vẫn là khía cạnh riêng. Tương tự, generic type metadata và tên tham số là những trục thông tin khác nhau.

## 6. Những giới hạn cần hiểu đúng

### 6.1 Chỉ lưu tên khai báo, không lưu giá trị runtime

`getParameters()` đọc phần **định nghĩa method hoặc constructor**. Nó không biết các lần gọi có truyền `"customer-01"`, `42` hay `null`; không chứa lịch sử lời gọi và không thể tự đọc biến trên stack của thread đang chạy.

Nếu cần quan sát đối số đang thực thi, đó là công việc của debugger, instrumentation, logging hoặc cơ chế quan sát runtime khác, với các hạn chế và yêu cầu riêng.

### 6.2 Không có named arguments trong cú pháp Java

Có metadata tên tham số **không** làm cú pháp sau trở nên hợp lệ:

~~~java
// Đây là ví dụ CÚ PHÁP SAI trong Java.
multiply(left: 6, right: 7);
~~~

Lời gọi Java hợp lệ với method ở ví dụ là:

~~~java
// Minh họa câu lệnh trong lớp có method multiply(int, int).
int product = multiply(6, 7);
~~~

`-parameters` không bổ sung default argument, không thay đổi thứ tự truyền đối số và không làm compiler kiểm tra tên đầu vào theo quy tắc một framework.

### 6.3 Không tạo validation hoặc nội dung mô tả tham số

Nếu tên là `email`, compiler không tự kiểm tra địa chỉ email. Nếu tên là `amount`, metadata không thể hiện nó phải dương hay phải là tiền tệ. Tên không bao gồm tài liệu JavaDoc, contract nullability hoặc quy tắc nghiệp vụ.

Nếu framework muốn kiểm tra dữ liệu, nó cần nguồn quy tắc khác: annotation, schema, code validator hoặc cấu hình tường minh.

### 6.4 Không sửa được dependency đã biên dịch trước

Một ứng dụng có thể gồm source của chính bạn, class do code generator tạo và nhiều JAR thư viện. Bật cờ cho source của module **không thêm metadata vào JAR từ nơi khác**.

Ví dụ:

~~~text
application.jar: được build với -parameters
library.jar: được build không có -parameters
~~~

Reflection trên method của `application.jar` có thể thấy tên thật, nhưng method của `library.jar` vẫn trả `arg0`. Muốn library có metadata, nó phải được biên dịch/đóng gói thích hợp tại nguồn hoặc được xử lý bằng công cụ có khả năng thêm metadata đáng tin cậy.

### 6.5 Bytecode transformer có thể xóa hoặc thay đổi tên

Một số quy trình build chạy thêm obfuscator, shrinker, optimizer, bytecode instrumentation hoặc công cụ đóng gói. Tùy cấu hình, chúng có thể giữ, đổi hoặc loại bỏ `MethodParameters`. Vì vậy, **kết quả `javap` ngay sau `javac` chưa chắc giống artifact cuối được triển khai**.

Nếu framework cần metadata, hãy kiểm tra **class file trong JAR cuối** hoặc class được JVM nạp thật. Một vài hệ thống có thể dùng class loader tùy biến hoặc sinh class động khiến việc truy nguồn method cần thận trọng.

### 6.6 Tham số không phải một phần của binary method signature theo tên

Đổi:

~~~java
void publish(String topic)
~~~

thành:

~~~java
void publish(String channel)
~~~

không làm đổi kiểu tham số hay method descriptor ở JVM. Code đã compile khác có thể vẫn gọi được phương thức đó như cũ. Tuy nhiên, một framework dùng tên làm key có thể đổi hành vi từ binding `topic` sang `channel`.

Tên tham số vì thế **có thể trở thành hợp đồng ở tầng framework** ngay cả khi không phải yếu tố quyết định tương thích nhị phân. Nếu dùng tên trong API route, query mapping hoặc constructor binding, hãy quản lý đổi tên như thay đổi hợp đồng dữ liệu.

### 6.7 Compiler-generated, implicit và synthetic parameters

Ở một số construct Java, compiler tạo thêm tham số hoặc method phục vụ thực thi. `Parameter[]` có thể chứa các tham số không rõ ràng từ chữ ký source. Các cờ `isImplicit()` và `isSynthetic()` giúp xem metadata tương ứng khi có, nhưng không nên xây dựng logic dựa trên giả định mọi compiler/transformer tạo và giữ metadata giống nhau.

Điều này quan trọng khi phản chiếu constructor của non-static inner class, enum, hoặc phương thức do compiler/framework tạo. Khi xây binder, cần quan sát **declaring class**, loại executable, kiểu tham số, số lượng tham số và các cờ, chứ không chỉ tên.

### 6.8 Thông tin hiện diện có thể lộ cấu trúc nghiệp vụ

Tên `customerNumber`, `transactionLimit` hoặc `internalFlag` có thể tiết lộ một phần vocabulary của ứng dụng qua class file được phân phối. `-parameters` không phải một tính năng bảo mật. Không đặt bí mật vào source/metadata và không dựa vào việc thiếu metadata để giữ bí mật cho một sản phẩm phân phối ra ngoài.

Các công cụ obfuscation có thể đổi tên, nhưng nếu framework dựa vào tên thì cần cấu hình chính sách giữ/ánh xạ phù hợp. Không nên giả định vừa obfuscate toàn bộ tên vừa giữ nguyên một cơ chế runtime binding bằng tên.

## 7. Interface, kế thừa và method được phản chiếu

Tên formal parameter gắn với **từng khai báo method**, không được kế thừa theo nghĩa tên của method override bắt buộc giữ nguyên.

Tạo file **`src/DeclarationNamesDemo.java`**:

~~~java
import java.lang.reflect.Method;

interface Processor {
    void process(String input);
}

class UpperProcessor implements Processor {
    @Override
    public void process(String text) {
        System.out.println(text.toUpperCase());
    }
}

public class DeclarationNamesDemo {
    public static void main(String[] args) throws Exception {
        Method onInterface =
                Processor.class.getMethod("process", String.class);
        Method onClass =
                UpperProcessor.class.getMethod("process", String.class);

        System.out.println(onInterface.getParameters()[0].getName());
        System.out.println(onClass.getParameters()[0].getName());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -parameters -encoding UTF-8 -d out/with src/DeclarationNamesDemo.java
java -cp out/with DeclarationNamesDemo
~~~

Stdout:

~~~text
input
text
~~~

Hai khai báo hợp lệ để override vì quy tắc override dựa trên chữ ký phương thức phù hợp, không yêu cầu tên `input` và `text` trùng nhau.

Một framework phản chiếu `Processor.class` có thể thấy `input`, còn framework phản chiếu `UpperProcessor.class` thấy `text`. Nếu framework dùng proxy, bridge methods hoặc một lớp được sinh động, tên trả về còn phụ thuộc **method cụ thể đang được phản chiếu**. Đừng chỉ dựa trên method name mà bỏ qua `Method.getDeclaringClass()` và phương thức trong class triển khai.

Nếu bạn tự xây thư viện binding và muốn lấy tên từ interface, phải đưa ra quy tắc rõ ràng về nơi lấy tên và cách xử lý khi interface/implementation khác nhau. `-parameters` không tự hợp nhất các tên đó.

## 8. Framework sử dụng tên tham số như thế nào?

Nhiều thư viện có thể dùng tên tham số runtime để:

- Ánh xạ tên query, path hoặc command argument với tham số của method xử lý.
- Chọn giá trị cho constructor khi tạo đối tượng từ dữ liệu có tên.
- Tạo thông báo lỗi, tài liệu hoặc metadata phục vụ developer tooling.
- Kết nối đầu vào trong dependency-injection hoặc serializer theo hợp đồng riêng.

Tuy nhiên, **không phải mọi framework đều tự bật tính năng này**. Một framework có thể ưu tiên tên khai báo trong annotation, lấy tên từ Reflection, đọc metadata đặc thù hoặc bỏ qua tên parameter hoàn toàn.

Ví dụ khái niệm: khi handler định nghĩa `find(String orderId)`, một framework hỗ trợ suy luận tên có thể bind input key `orderId` dựa vào `MethodParameters`. Một framework khác có thể yêu cầu annotation khai báo rõ tên, hoặc có cơ chế khác. Phải đọc contract của framework đang dùng.

Với public API, đặt tên tường minh ở annotation/config thường giúp ổn định hành vi nếu sau này đổi tên biến Java. Nếu chọn suy luận tên bằng Reflection, phải đảm bảo pipeline biên dịch **giữ metadata ở mọi module liên quan** và có kiểm thử cho hành vi binding.

### Không dùng metadata để suy luận kiểu hoặc giá trị mặc định

Nếu `Parameter.getName()` trả `timeout`, bạn vẫn cần xem kiểu tham số từ `getType()`, annotation và rules để biết cách parse đầu vào. `timeout` có thể là `int`, `long` hoặc `Duration`. Tên không biến đổi kiểu và không quyết định một giá trị default.

## 9. Cấu hình thực tế với compiler và build tool

Một nguyên tắc chung: cờ phải được truyền tới **compiler xử lý source chứa method/constructor mà bạn đọc**, sau đó class file thực sự được nạp trong runtime phải giữ metadata tương ứng.

### 9.1 Lệnh `javac` trực tiếp

~~~bash
javac -parameters -encoding UTF-8 -d out/with src/ParameterNamesDemo.java
~~~

Khi cần tương thích Java 17 và đang dùng JDK hỗ trợ tùy chọn đó:

~~~bash
javac --release 17 -parameters -encoding UTF-8 -d out/with src/ParameterNamesDemo.java
~~~

`--release 17` quy định mức ngôn ngữ, API Java platform và class-file target phù hợp Java 17; `-parameters` lưu metadata tên tham số. Hai tùy chọn giải quyết **hai nhu cầu khác nhau**. Không dùng `--release` để thay cho `-parameters`.

### 9.2 Gradle Groovy DSL

Trong `build.gradle` của module áp dụng Java plugin, có thể thêm:

~~~groovy
tasks.withType(org.gradle.api.tasks.compile.JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
~~~

Điều này áp dụng với các task `JavaCompile` được cấu hình trong module đó, nếu compiler/toolchain hỗ trợ. Dự án nhiều module có thể cần thiết lập ở nhiều nơi hoặc dùng convention plugin chung.

Với **Gradle Kotlin DSL** trong `build.gradle.kts`:

~~~kotlin
tasks.withType<org.gradle.api.tasks.compile.JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Đây là ví dụ cấu hình build, không phải đoạn Java source. Nếu dự án có tác vụ compile riêng cho test hoặc generated sources, hãy xem chúng có nhận cờ hay không. Sau khi thay cấu hình, cần build lại các class liên quan.

### 9.3 Maven

Trong `pom.xml` của module, phần cấu hình compiler plugin có thể viết:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là **đoạn XML cần đặt trong cấu hình Maven hợp lệ**, không phải toàn bộ file `pom.xml` độc lập. Hãy dùng phiên bản plugin phù hợp, có hỗ trợ cấu hình `parameters`; phiên bản thực tế có thể do `pluginManagement` của project quyết định.

Nếu các module dùng cấu hình compiler khác nhau, việc bật `parameters` ở module A không tự ghi tên của class thuộc module B. Khi nhận một thư viện third-party JAR, tùy chọn Maven/Gradle của project hiện tại cũng không tự thay đổi metadata trong JAR đó.

### 9.4 Kiểm tra sau build, tránh tin vào cấu hình trên giấy

Để xác minh cấu hình hiệu lực:

1. Build lại module bằng công cụ bạn thực sự dùng.
2. Xác định thư mục output class hoặc JAR build cuối, tránh chạy lớp cũ.
3. Dùng `javap -v -p` mở đúng class file đó; xem `MethodParameters` của một method có tên dễ nhận biết.
4. Chạy một đoạn Reflection dùng `isNamePresent()` ngay trên runtime classpath cuối.
5. Nếu ứng dụng đã qua obfuscation/instrumentation, thực hiện kiểm tra **sau bước đó**.

Ví dụ đối với cấu trúc bài thực hành:

~~~bash
javap -v -p -classpath out/with ParameterNamesDemo
java -cp out/with ParameterNamesDemo
~~~

Với Gradle/Maven, hãy thay `out/with` bằng đường dẫn output thật được công cụ tạo; không đoán rằng hệ thống luôn dùng thư mục giống ví dụ.

### 9.5 Không nhầm compiler flag với JVM option

`-parameters` là **tùy chọn của `javac`**. Việc chỉ chạy `java -parameters ...` không phải cách làm cho class file vốn thiếu tên tự có thêm metadata. JVM đọc class đã được tạo; tên phải hiện diện trong artifact mà JVM nạp. Tương tự, JVM có thể chạy class file có `MethodParameters` mà không phải được truyền `-parameters` khi khởi động.

Câu dễ nhớ:

~~~text
javac -parameters ...  -> tạo metadata tên trong .class
java -cp ...          -> nạp .class và đọc metadata bằng Reflection
~~~


## 10. Viết code an toàn nếu tên có thể thiếu

Nếu logic của bạn đòi hỏi tên tham số thực, hãy xử lý thiếu metadata tường minh. Tạo file **`src/RequireNamesDemo.java`**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class RequireNamesDemo {
    public static void greet(String person) {
        System.out.println("Hello, " + person);
    }

    public static void main(String[] args) throws Exception {
        Method method =
                RequireNamesDemo.class.getDeclaredMethod("greet", String.class);

        Parameter parameter = method.getParameters()[0];
        if (!parameter.isNamePresent()) {
            System.out.println("Missing parameter-name metadata");
            return;
        }

        System.out.println("Parameter name = " + parameter.getName());
        greet("An");
    }
}
~~~

Không có cờ:

~~~bash
javac -encoding UTF-8 -d out/without src/RequireNamesDemo.java
java -cp out/without RequireNamesDemo
~~~

Stdout:

~~~text
Missing parameter-name metadata
~~~

Có cờ:

~~~bash
javac -parameters -encoding UTF-8 -d out/with src/RequireNamesDemo.java
java -cp out/with RequireNamesDemo
~~~

Stdout:

~~~text
Parameter name = person
Hello, An
~~~

Ví dụ này chọn thông báo rồi `return` khi metadata thiếu. Một hệ thống thật có thể **fail fast** với exception và hướng dẫn bật compiler flag, hoặc fallback sang tên khai báo tường minh trong annotation. Quan trọng là tránh âm thầm dùng `arg0` làm tên input nghiệp vụ nếu nó không được quy định trong contract.

**Không được suy ra:** “`isNamePresent()` trả `true` thì framework đã binding đúng.” Kết quả đó mới xác nhận một phần: tên parameter có sẵn. Bạn còn cần kiểm tra input có đúng tên, đúng kiểu, đúng validation, đúng nguồn dữ liệu và đúng quy tắc framework hay không.

## 11. Các lỗi thường gặp và cách kiểm tra

| Triệu chứng | Khả năng nguyên nhân | Cách xác minh |
| --- | --- | --- |
| `getName()` trả `arg0` và `isNamePresent()` là `false` | Class không chứa metadata tên formal parameter | Build lại module với `-parameters`, kiểm tra `javap` trên class cuối |
| Bật `-g` rồi vẫn không đọc được tên | Debug metadata không thay thế `MethodParameters` | Dùng `-parameters` |
| Tên cũ xuất hiện sau khi đổi source | Class/JAR cũ vẫn được nạp | Kiểm tra `-cp`, build output, deploy artifact và classpath |
| Build tool có cấu hình nhưng tên vẫn thiếu | Cờ ở sai module/task hoặc compile cache chưa cập nhật artifact đang chạy | Xác minh compiler arguments, class file và artifact cuối |
| Method interface có tên khác implementation | Metadata thuộc từng khai báo | Kiểm tra `getDeclaringClass()` và khai báo framework đang đọc |
| Constructor có số tham số lạ | Compiler có thể tạo implicit/synthetic parameter | Đọc `getParameters()`, cờ và bytecode thực |
| Framework không bind dù tên đã hiện diện | Framework dùng quy tắc mapping/annotation khác | Xem tài liệu và cấu hình framework, kiểm tra input/kiểu |
| Reflection đúng ở local nhưng sai khi deploy | Packaging, transformer, obfuscation hoặc runtime classpath khác | So sánh artifact được deploy và class thực tế nạp |
| `Parameter.getName()` trả `arg0` nhưng `isNamePresent()` là `true` | Tên thật trong source có thể là `arg0` | Tin vào cờ và metadata, không đoán chỉ từ chuỗi |
| Thư viện A có metadata, B không có | Các JAR đã được build với cấu hình khác nhau | Xem từng method/constructor trên class tương ứng |

### Đừng lẫn compile-time và runtime

`javac` hoàn toàn có thể tạo class hợp lệ khi không có cờ `-parameters`. Bản class đó vẫn chạy, JVM vẫn biết số lượng/kiểu tham số, vẫn có thể gọi method và constructor. Chỉ những API/framework cần tên trong source mới thấy khác biệt.

Ngược lại, compiler có thể ghi metadata đầy đủ nhưng runtime binding vẫn lỗi vì tên đầu vào không khớp, thiếu annotation, kiểu không thể chuyển đổi hoặc dữ liệu thực tế không hợp lệ. Đây là các lỗi thuộc hợp đồng ứng dụng, không phải một thất bại của `-parameters`.

## 12. Bài tập thực hành và đáp án

### Bài 1 — Đối chiếu hai class file

Dùng `ParameterNamesDemo` ở mục 3. Build cùng source vào `out/without` và `out/with`. So sánh ba thuộc tính tên, `isNamePresent()` và kiểu.

**Đáp án:** Không cờ: `arg0`/`arg1`, `false`, `int`. Có cờ: `left`/`right`, `true`, `int`. Phép nhân luôn cho `42`.

### Bài 2 — Tắt debug nhưng vẫn lưu tên

Thực hiện:

~~~bash
javac -parameters -g:none -encoding UTF-8 -d out/with src/ParameterNamesDemo.java
java -cp out/with ParameterNamesDemo
~~~

**Đáp án:** Tên vẫn là `left`/`right` nếu compiler lưu `MethodParameters`; `-g:none` không xóa thuộc tính này. Điều này chứng minh debug metadata và metadata tên formal parameter khác nhau.

### Bài 3 — Kiểm tra constructor

Biên dịch `ConstructorNamesDemo` với hai cấu hình; giải thích vì sao output `Sách: 3` không đổi.

**Đáp án:** Metadata tên chỉ tác động phần phản chiếu, không đổi bytecode gán các field trong constructor.

### Bài 4 — Kiểm tra override

Biên dịch `DeclarationNamesDemo` có cờ, giải thích tại sao interface trả `input` và class triển khai trả `text`.

**Đáp án:** Tên gắn với từng khai báo, không tham gia quy tắc override theo chữ ký JVM.

### Bài 5 — Nhận diện metadata thiếu

Chạy `RequireNamesDemo` không có cờ. Vì sao code không gọi `greet("An")`?

**Đáp án:** `isNamePresent()` trả `false` nên nhánh thiếu metadata in thông báo rồi kết thúc `main`. Đây là lựa chọn chủ động của code ứng dụng, không phải hành vi tự động của JVM.

### Bài 6 — Dự án nhiều module

Module `api` chứa interface có method `handle(String requestId)`; module `impl` chứa implementation khai báo `handle(String id)`. Chỉ `impl` bật cờ. Một framework phản chiếu phương thức của `api` sẽ được đảm bảo thấy `requestId` không?

**Đáp án:** Không. Phải kiểm tra class của `api` có được biên dịch/đóng gói với metadata không. Tên của implementation không tự chuyển sang method thuộc interface.

## 13. Câu hỏi tự kiểm tra

**`-parameters` có tác động đến chữ ký nhị phân phương thức không?** Nó thêm metadata tên; phần tên không trở thành thành phần quyết định descriptor của một method Java.

**Có thể đọc tên của mọi biến cục bộ bằng `Parameter.getName()` không?** Không; chỉ các formal parameters của method/constructor được phản chiếu.

**`arg0` luôn là tên do JVM tự tạo?** Không; phải xem `isNamePresent()`. Người lập trình có thể thực sự chọn tên `arg0`.

**Bật cờ trên project có sửa JAR thư viện bên ngoài không?** Không; phải xem class/JAR được biên dịch và đóng gói bằng cách nào.

**Tên tham số có thể trở thành một phần contract của framework không?** Có. Dù không quyết định binary signature, nó có thể được framework dùng làm tên khóa binding.

**Dùng `-parameters` có đủ bảo đảm input hợp lệ không?** Không. Đó là metadata tên, còn validation, kiểu, default, annotation và dữ liệu đầu vào thuộc các cơ chế khác.

## 14. Ghi nhớ

`javac -parameters` giúp giữ **tên formal parameters trong `MethodParameters`** để Java Reflection đọc được khi chạy. Hãy đối chiếu `Parameter.getName()` với `Parameter.isNamePresent()`, phân biệt nó với `-g` và biến cục bộ, rồi kiểm tra artifact cuối ở đúng module. Khi framework dựa vào tên tham số để ánh xạ đầu vào, sự tồn tại và tính ổn định của metadata trở thành một phần cần kiểm thử trong quy trình build và triển khai.