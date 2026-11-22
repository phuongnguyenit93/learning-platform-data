# Không tạo thêm hằng enum bằng Constructor.newInstance

## 1. Enum không phải lớp thường có constructor riêng tư

Một enum khai báo một tập các hằng có tên. Ví dụ:

~~~java
enum Phase {
    READY, DONE;
}
~~~

Trong khai báo này, `READY` và `DONE` là các hằng của `Phase`. Các đối tượng tương ứng được tạo trong quá trình khởi tạo lớp enum.

Khi học Reflection, ta dễ suy luận rằng:

1. Enum có constructor.
2. Constructor đó không `public`.
3. Nếu lấy constructor và mở quyền truy cập thì có thể gọi `newInstance()` để tạo `EXTRA`.

**Suy luận ở bước 3 không đúng.** `Constructor.newInstance()` có quy tắc riêng: nếu constructor thuộc một lớp enum, việc tạo instance bị từ chối bằng `IllegalArgumentException`. Đây không chỉ là vấn đề constructor có modifier `private`.

Quy tắc được ghi trong hợp đồng [Constructor.newInstance](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)). [JLS §8.9](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.9) cũng nêu rằng không được tạo instance enum bằng Reflection.

Bài học này tập trung vào việc phân biệt **khảo sát constructor**, **điều chỉnh kiểm tra truy cập** và **được phép tạo đối tượng**. Có được hai điều đầu không có nghĩa điều thứ ba được cho phép.

## 2. Vì sao enum vẫn có constructor?

Constructor của enum phục vụ việc khởi tạo các hằng được khai báo. Nó có thể nhận dữ liệu riêng, gán trường và thực hiện logic khởi tạo giống những phần mã Java thông thường.

Ví dụ sau là một khai báo enum độc lập:

~~~java
enum Severity {
    LOW(1),
    HIGH(5);

    private final int score;

    Severity(int score) {
        this.score = score;
    }
}
~~~

Khi các hằng được khởi tạo, `LOW` nhận dữ liệu `1`, còn `HIGH` nhận dữ liệu `5`. Điều đó không tạo một API để mã bên ngoài gọi `new Severity(3)`.

Một vài quy tắc cần nhớ:

- Không được dùng biểu thức `new` để tự tạo instance của lớp enum.
- Constructor enum không được khai báo `public` hoặc `protected`.
- Constructor enum không ghi modifier truy cập được xem là `private`.
- Việc Reflection nhìn thấy constructor không làm thay đổi các quy tắc của enum.

Đặc biệt, `private` và “không được tạo thêm instance enum bằng `Constructor.newInstance()`” là hai ràng buộc khác nhau. Thí nghiệm tiếp theo tách rõ chúng.

## 3. Thí nghiệm đầy đủ: cùng mở truy cập, kết quả khác nhau

Lưu toàn bộ mã dưới đây vào `EnumConstructorDemo.java`. Chỉ lớp `EnumConstructorDemo` là `public`; các lớp và enum hỗ trợ ở cấp cao nhất nằm trong cùng tệp.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Modifier;
import java.util.Arrays;

final class PlainItem {
    private PlainItem() {
    }
}

final class PhaseConstructionCount {
    static int count;
}

enum Phase {
    READY, DONE;

    private Phase() {
        PhaseConstructionCount.count++;
    }
}

public class EnumConstructorDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        Constructor<PlainItem> plain =
                PlainItem.class.getDeclaredConstructor();

        System.out.println("plain private: "
                + Modifier.isPrivate(plain.getModifiers()));
        System.out.println("plain accessible before: "
                + plain.canAccess(null));
        System.out.println("plain access enabled: "
                + plain.trySetAccessible());
        System.out.println("plain created: "
                + (plain.newInstance() != null));

        System.out.println("enum public constructors: "
                + Phase.class.getConstructors().length);

        try {
            Phase.class.getDeclaredConstructor();
            throw new AssertionError("Unexpected no-arg constructor");
        } catch (NoSuchMethodException expected) {
            System.out.println("enum no-arg lookup: NoSuchMethodException");
        }

        Constructor<Phase> constructor =
                Phase.class.getDeclaredConstructor(String.class, int.class);

        System.out.println("enum parameters: "
                + Arrays.toString(constructor.getParameterTypes()));
        System.out.println("enum private: "
                + Modifier.isPrivate(constructor.getModifiers()));
        System.out.println("enum accessible before: "
                + constructor.canAccess(null));
        System.out.println("enum access enabled: "
                + constructor.trySetAccessible());
        System.out.println("enum accessible after: "
                + constructor.canAccess(null));

        System.out.println("values before: "
                + Arrays.toString(Phase.values()));
        int callsBefore = PhaseConstructionCount.count;
        System.out.println("constructor calls before: " + callsBefore);

        try {
            constructor.newInstance("EXTRA", 2);
            throw new AssertionError("Enum construction unexpectedly succeeded");
        } catch (IllegalArgumentException expected) {
            System.out.println("enum newInstance: IllegalArgumentException");
        }

        System.out.println("constructor body unchanged: "
                + (PhaseConstructionCount.count == callsBefore));
        System.out.println("values after: "
                + Arrays.toString(Phase.values()));

        try {
            Enum.valueOf(Phase.class, "EXTRA");
            throw new AssertionError("Unexpected EXTRA constant");
        } catch (IllegalArgumentException expected) {
            System.out.println("lookup EXTRA: IllegalArgumentException");
        }

        System.out.println("lookup READY identity: "
                + (Enum.valueOf(Phase.class, "READY") == Phase.READY));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 EnumConstructorDemo.java
java EnumConstructorDemo
~~~

Kết quả chính xác khi chạy theo các lệnh trên, trên classpath thông thường:

~~~text
plain private: true
plain accessible before: false
plain access enabled: true
plain created: true
enum public constructors: 0
enum no-arg lookup: NoSuchMethodException
enum parameters: [class java.lang.String, int]
enum private: true
enum accessible before: false
enum access enabled: true
enum accessible after: true
values before: [READY, DONE]
constructor calls before: 2
enum newInstance: IllegalArgumentException
constructor body unchanged: true
values after: [READY, DONE]
lookup EXTRA: IllegalArgumentException
lookup READY identity: true
~~~

Chương trình in loại ngoại lệ, không phụ thuộc vào nguyên văn thông báo lỗi của một phiên bản JDK.

`PlainItem` và `Phase` là các kiểu ở cấp cao nhất, tách khỏi lớp chứa `main()`. Cách đặt này giúp thể hiện rõ trạng thái không truy cập được constructor `private` trước khi gọi `trySetAccessible()`.

### 3.1. Lớp thường có thể được tạo sau khi mở truy cập

Đối với `PlainItem`:

- Constructor là `private`.
- Trước khi mở truy cập, `canAccess(null)` trả về `false`.
- Trong môi trường của thí nghiệm, `trySetAccessible()` trả về `true`.
- `plain.newInstance()` tạo được một đối tượng.

Điều này làm mẫu đối chiếu cho nhận định “constructor riêng tư có thể gọi được khi điều kiện truy cập cho phép”. Nó không áp dụng riêng cho enum.

### 3.2. Enum vẫn bị từ chối dù đã mở truy cập

Đối với constructor của `Phase`, chương trình cũng xác nhận:

~~~text
enum private: true
enum accessible before: false
enum access enabled: true
enum accessible after: true
~~~

Ngay sau đó, lời gọi:

~~~java
constructor.newInstance("EXTRA", 2);
~~~

vẫn ném `IllegalArgumentException`.

Như vậy, lỗi không xuất phát từ việc chưa mở quyền truy cập constructor trong thí nghiệm này. Trạng thái truy cập đã được chứng minh là cho phép; quy tắc cấm tạo instance enum vẫn còn hiệu lực.

`canAccess(null)` chỉ hỏi người gọi hiện tại có thể truy cập đối tượng Reflection đó hay không. Nó không hỏi rằng mọi thao tác thực thi tiếp theo đều hợp lệ về ngữ nghĩa. Đối với constructor, đối số của `canAccess` phải là `null`; đây không phải một đối tượng sẽ nhận lời gọi phương thức.

### 3.3. Thân constructor không được gọi thêm

Để quan sát điều này, constructor của `Phase` tăng một bộ đếm nằm ở lớp hỗ trợ riêng:

~~~java
private Phase() {
    PhaseConstructionCount.count++;
}
~~~

Trước thí nghiệm tạo thêm instance, chương trình gọi `Phase.values()` để khởi tạo hai hằng hiện có. Vì vậy bộ đếm là `2`.

Sau lần `newInstance()` bị từ chối:

- Bộ đếm giữ nguyên.
- `Phase.values()` vẫn chỉ chứa `READY` và `DONE`.
- Tra cứu `EXTRA` bằng `Enum.valueOf(...)` vẫn thất bại.

Bộ đếm ở ngoài enum cũng giúp tránh trộn bài thí nghiệm với các quy tắc đặc biệt về truy cập trường tĩnh trong quá trình khởi tạo enum.

## 4. Vì sao tìm constructor không tham số lại thất bại?

Mã nguồn có thể cho thấy:

~~~java
private Phase() {
    PhaseConstructionCount.count++;
}
~~~

nhưng metadata constructor trong class file do `javac` tạo ở ví dụ này có các tham số:

~~~text
[class java.lang.String, int]
~~~

Chúng phục vụ tên hằng và vị trí thứ tự của hằng. Constructor của lớp cơ sở `Enum` nhận `name` và `ordinal`; các giá trị này được mã do trình biên dịch sinh ra cung cấp.

Vì vậy, trong thí nghiệm:

~~~java
Phase.class.getDeclaredConstructor();
~~~

không tìm thấy constructor có danh sách kiểu tham số rỗng và ném `NoSuchMethodException`.

Tra cứu tương ứng với metadata đã quan sát là:

~~~java
Phase.class.getDeclaredConstructor(String.class, int.class);
~~~

**Tìm được chữ ký không có nghĩa được gọi để tạo enum.** Ví dụ đã truyền đúng hai đối số có kiểu phù hợp nhưng vẫn bị chặn.

Nếu enum có tham số do người viết khai báo, chẳng hạn `Severity(int score)`, metadata do `javac` sinh thường thể hiện các tham số hỗ trợ ở trước tham số `score`. Khi khảo sát constructor, hãy xem `getParameterTypes()` và metadata thực tế của class file, không suy đoán từ số tham số nhìn thấy trong mã nguồn. Không dùng vị trí đầu tiên của `getDeclaredConstructors()` làm quy tắc chọn constructor khi enum có nhiều constructor.

Cũng không nên dựa vào tên tham số như `arg0` hay tên nội bộ do compiler đặt. Tùy chọn biên dịch và metadata có thể ảnh hưởng cách tên tham số được phản chiếu.

`String.class` và `int.class` trong ví dụ là các **kiểu dùng để tìm chữ ký**. Truyền `Integer.class` thay `int.class` cho `getDeclaredConstructor(...)` không phải cùng một tra cứu. Việc `newInstance()` có hỗ trợ chuyển đổi đối số ở bước gọi không làm API tìm constructor tự chọn lại một chữ ký khác.

## 5. Phân biệt các thao tác và nhóm lỗi

| Thao tác hoặc tình huống | Ý nghĩa và kết quả cần phân biệt |
| --- | --- |
| `getConstructors()` | Chỉ trả constructor `public`; enum trong ví dụ có mảng rỗng |
| `getDeclaredConstructor(...)` | Tìm constructor khai báo trong lớp, bao gồm constructor riêng tư; chữ ký không khớp gây `NoSuchMethodException` |
| Constructor chưa truy cập được | Khi gọi, có thể gặp `IllegalAccessException` |
| `trySetAccessible()` | Thử cho phép bỏ qua kiểm tra truy cập theo các điều kiện của Java; thành công không bỏ quy tắc cấm tạo enum |
| `setAccessible(true)` không được môi trường cho phép | Có thể gặp `InaccessibleObjectException` hoặc kiểm tra bảo mật tương ứng |
| `newInstance()` với constructor enum đã truy cập được | Việc tạo instance enum bị từ chối bằng `IllegalArgumentException` |
| Đối số gọi sai số lượng hoặc kiểu | Cũng có thể gây `IllegalArgumentException`; không được suy từ tên ngoại lệ rằng luôn do enum |
| Thân constructor hợp lệ tự ném ngoại lệ | Thông thường ngoại lệ từ thân constructor được bọc trong `InvocationTargetException` |

Bảng giúp định vị vấn đề ở đúng thao tác. Không nên gộp mọi thất bại Reflection thành “không tìm thấy constructor” hoặc “thiếu quyền”.

### IllegalArgumentException ở đây không phải ngoại lệ từ thân constructor

Trong thí nghiệm, Reflection từ chối tạo đối tượng enum; thân constructor không chạy thêm. Vì vậy không có một ngoại lệ do thân constructor `Phase()` tự ném rồi được bọc lại.

Nếu chỉ bắt:

~~~java
// Đoạn minh họa cho một khối catch chưa đủ để xử lý trường hợp enum.
catch (java.lang.reflect.InvocationTargetException ex) {
    System.out.println(ex.getCause());
}
~~~

thì chưa xử lý được `IllegalArgumentException` phát sinh do quy tắc cấm tạo enum. Đoạn trên chỉ là nhánh `catch` minh họa, phải đặt sau một khối `try` thích hợp khi dùng trong mã Java.

Trong ứng dụng, hãy đọc lỗi cùng với **kiểu đang tạo**, **constructor đã tìm**, **quyền truy cập** và **đối số thực tế**. Không chỉ kiểm tra chuỗi thông báo của ngoại lệ.

## 6. setAccessible không phải công tắc bỏ mọi ràng buộc

`setAccessible(true)` và `trySetAccessible()` làm việc với kiểm tra truy cập của Reflection, trong giới hạn mà hệ thống module và môi trường cho phép.

Chúng không:

- Thêm một hằng vào khai báo enum.
- Thay đổi lớp enum thành lớp thường.
- Thay đổi số lượng hoặc kiểu tham số của constructor.
- Biến việc tạo enum bằng `Constructor.newInstance()` thành thao tác hợp lệ.

Thí nghiệm dùng các kiểu do chính chương trình định nghĩa trên classpath, nên việc mở truy cập thành công. Khi khảo sát một kiểu ở module khác, việc mở truy cập có thể thất bại trước khi đi đến câu hỏi tạo đối tượng.

Tài liệu [AccessibleObject.trySetAccessible](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html#trySetAccessible()) mô tả giới hạn của thao tác này. Nếu mở được quyền truy cập thì quy tắc enum vẫn giữ nguyên; thay đổi cấu hình mở package không phải cách sửa lỗi cấm tạo enum.

Cũng cần phân biệt **metadata có thể đọc được** với **thao tác có thể thực hiện**. Công cụ có thể hiển thị constructor enum để phục vụ khảo sát chữ ký, annotation hoặc bytecode mà không cần và không được tạo thêm hằng bằng API này.

## 7. “Lấy hằng hiện có” khác với “tạo hằng mới”

Khi cần một giá trị enum từ dữ liệu đầu vào, thường mục tiêu thực tế là chọn một hằng đã được khai báo.

Ví dụ, trong ngữ cảnh chương trình trên:

~~~java
Phase ready = Enum.valueOf(Phase.class, "READY");
System.out.println(ready == Phase.READY);
~~~

Kết quả:

~~~text
true
~~~

`Enum.valueOf` không gọi constructor để tạo thêm `READY`. Nó trả về hằng hiện có mang đúng tên khai báo.

Nếu tên là `EXTRA`, API ném `IllegalArgumentException` vì enum không khai báo hằng đó. Không tự sinh một hằng mới và không tự thêm hằng vào `values()`.

| Nhu cầu | Cách biểu diễn phù hợp |
| --- | --- |
| Chọn hằng có tên đã biết khi viết mã | `Phase.READY` |
| Chuyển tên khai báo thành hằng hiện có | `Enum.valueOf(Phase.class, name)` hoặc `Phase.valueOf(name)` |
| Liệt kê các hằng khi biết enum lúc biên dịch | `Phase.values()` |
| Liệt kê khi chỉ có token lớp | `enumType.getEnumConstants()` |
| Bổ sung hằng cho mô hình enum | Thay đổi khai báo enum và xây dựng lại chương trình |
| Tập giá trị cần thêm hoặc xóa trong lúc chạy | Mô hình dữ liệu có thể mở rộng, chẳng hạn lớp hoặc record kết hợp danh mục đăng ký |

Khi đọc tên từ đầu vào, phải có chính sách xử lý tên không hợp lệ, khác biệt chữ hoa/chữ thường hoặc nhãn hiển thị. `Enum.valueOf` dùng đúng tên khai báo, không dùng chuỗi tùy biến từ `toString()`. Quy tắc API được nêu tại [Enum.valueOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Enum.html#valueOf(java.lang.Class,java.lang.String)).

Không dùng constructor Reflection làm nhánh dự phòng khi `valueOf` không tìm thấy tên. Hai việc đó không tương đương nhau.

## 8. Tác động đến công cụ tạo đối tượng tổng quát

Một bộ ánh xạ dữ liệu hoặc factory dựa trên Reflection không nên xử lý enum theo nhánh “tìm constructor không tham số rồi tạo đối tượng”.

Với enum, thông thường cần một **quy tắc chọn hằng** dựa trên dữ liệu: tên khai báo, mã nghiệp vụ đã được định nghĩa, hoặc một ánh xạ do ứng dụng cung cấp.

Một hàm minh họa cho nhánh tạo đối tượng mặc định có thể từ chối enum ngay từ đầu:

~~~java
// Phương thức hỗ trợ; đặt trong một lớp và thêm import java.util.Objects.
static <T> T createDefault(Class<T> type)
        throws ReflectiveOperationException {
    Objects.requireNonNull(type, "type");

    if (type.isEnum()) {
        throw new IllegalArgumentException(
                "Supply an existing enum constant: " + type.getName());
    }

    return type.getDeclaredConstructor().newInstance();
}
~~~

Hàm này chỉ minh họa chính sách không tạo enum bằng constructor. Với lớp thường, nó vẫn yêu cầu một constructor không tham số truy cập được; nó không tự giải quyết mọi trường hợp của một framework tạo đối tượng.

Ví dụ lời gọi khi thêm hàm vào chương trình mẫu:

~~~java
System.out.println(createDefault(StringBuilder.class).length());

try {
    createDefault(Phase.class);
} catch (IllegalArgumentException expected) {
    System.out.println("enum requires an existing constant");
}
~~~

Kết quả của riêng đoạn thêm:

~~~text
0
enum requires an existing constant
~~~

Việc kiểm tra sớm giúp công cụ đưa ra hướng xử lý đúng, thay vì liên tục thử các tổ hợp tham số hoặc mở truy cập rồi gặp lại cùng một quy tắc cấm của Reflection.

## 9. Những hiểu lầm thường gặp

**“Enum không có constructor nên Reflection không tạo được.”** Enum có constructor và có thể khảo sát được bằng Reflection. Hạn chế nằm ở việc tạo instance bằng `Constructor.newInstance()`, không phải ở sự tồn tại của constructor.

**“Chỉ cần setAccessible(true) vì constructor enum là private.”** Mở truy cập không bỏ quy tắc riêng cấm tạo enum.

**“Truyền thêm tên và ordinal là tạo được hằng mới.”** Các đối số hỗ trợ giải thích chữ ký do compiler sinh ra. Chúng không phải API mở rộng tập hằng enum.

**“NoSuchMethodException và IllegalArgumentException là cùng một lỗi.”** Một lỗi xảy ra khi không tìm thấy chữ ký constructor; lỗi còn lại trong thí nghiệm xảy ra khi gọi một constructor đã tìm được.

**“CanAccess trả true thì newInstance chắc chắn thành công.”** Quyền truy cập chỉ là một điều kiện. Enum vẫn bị từ chối; lớp thường cũng có thể thất bại vì các điều kiện khác hoặc vì thân constructor ném ngoại lệ.

**“Đổi thông báo lỗi hoặc bắt InvocationTargetException sẽ giúp tạo được enum.”** Xử lý ngoại lệ chỉ xử lý kết quả thất bại; không biến thao tác bị cấm thành hợp lệ.

**“ValueOf tạo mới enum theo tên yêu cầu.”** Nó chọn hằng đã tồn tại, không tạo hoặc đăng ký thêm hằng.

## 10. Tự kiểm tra

1. Vì sao chương trình có thể lấy được `Constructor<Phase>` nhưng không tạo được `EXTRA`?
2. Trong thí nghiệm, bằng chứng nào cho thấy việc mở quyền truy cập đã thành công?
3. Vì sao gọi `getDeclaredConstructor()` không tham số không tìm thấy constructor trong ví dụ do `javac` biên dịch?
4. Lỗi tạo enum sau khi đã mở truy cập có được bọc trong `InvocationTargetException` như một ngoại lệ từ thân constructor không?
5. Vì sao chỉ nhìn thấy `IllegalArgumentException` chưa đủ để khẳng định nguyên nhân là enum?
6. Sau lần thử tạo `EXTRA`, bộ đếm constructor và `Phase.values()` thay đổi thế nào?
7. Nếu muốn lấy `READY` từ chuỗi `"READY"`, nên gọi API nào?
8. Nếu danh mục nghiệp vụ phải bổ sung phần tử trong lúc chương trình chạy, có nên cố gọi constructor enum để làm việc đó không?

Đáp án:

1. Metadata constructor vẫn tồn tại; hợp đồng `Constructor.newInstance()` cấm tạo instance enum.
2. `trySetAccessible()` trả về `true` và `canAccess(null)` sau đó cũng trả về `true`.
3. Metadata trong ví dụ có hai tham số hỗ trợ `String` và `int`; tra cứu danh sách rỗng không khớp.
4. Không trong thí nghiệm này. Reflection từ chối bằng `IllegalArgumentException` trước khi thực thi thêm thân constructor enum.
5. Vì lỗi số lượng hoặc kiểu đối số cũng có thể gây loại ngoại lệ đó; phải đối chiếu ngữ cảnh.
6. Bộ đếm giữ nguyên ở `2`; danh sách hằng vẫn là `[READY, DONE]`.
7. Dùng `Enum.valueOf(Phase.class, "READY")` hoặc `Phase.valueOf("READY")`; kết quả là hằng hiện có.
8. Không. Hãy dùng một mô hình dữ liệu cho phép tập giá trị thay đổi trong lúc chạy.
