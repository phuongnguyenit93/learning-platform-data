# MalformedParametersException và metadata tham số không hợp lệ trong Java Reflection

## 1. Tình huống: phương thức tồn tại nhưng đọc danh sách tham số lại lỗi

Khi dùng Reflection, ta thường truy cập `Method` hoặc `Constructor` để đọc thông tin về tham số. Chẳng hạn framework có thể hỏi một phương thức nhận bao nhiêu tham số, kiểu gì và tên từng tham số là gì. Có những trường hợp class tải được, phương thức vẫn tồn tại, nhưng lệnh:

```java
Parameter[] parameters = method.getParameters();
```

ném `java.lang.reflect.MalformedParametersException`. Đây là dấu hiệu **metadata mô tả tham số trong file `.class` không hợp lệ** theo quy tắc của JVM/Reflection, không có nghĩa bản thân Java source đang gọi phương thức với đối số sai.

`MalformedParametersException` là một **unchecked exception**, kế thừa từ `RuntimeException`; có từ Java 8. API điển hình gây ra lỗi là `java.lang.reflect.Executable.getParameters()` (được `Method` và `Constructor` kế thừa). Lỗi có thể xuất hiện khi framework tự động dò constructor, binding tên tham số, làm dependency injection hoặc xử lý annotation và gọi API đọc metadata tương ứng.

Điều cần nhớ ngay:

- **Thiếu metadata tên tham số** thường là trường hợp hợp lệ: Java vẫn có thể tạo đối tượng `Parameter` với tên thay thế `arg0`, `arg1` và `isNamePresent() == false`.
- **Metadata hiện diện nhưng sai cấu trúc/nội dung** mới là nhóm lỗi mà `MalformedParametersException` mô tả.
- Cách sửa tốt nhất thường nằm ở **quá trình biên dịch/sinh/sửa bytecode**, không phải thêm `try/catch` quanh code nghiệp vụ rồi bỏ qua mọi lỗi.

## 2. Hiểu các lớp thông tin tham số trong class file

Một method/constructor có **method descriptor** ở cấp bytecode, xác định kiểu tham số và kiểu trả về. Ví dụ khai báo:

```java
public void submit(String orderId, int quantity) { }
```

có descriptor:

```text
(Ljava/lang/String;I)V
```

Descriptor xác định phương thức nhận `String` và `int`, trả về `void`. **Descriptor không chứa tên `orderId` hoặc `quantity`.**

Từ Java 8, class file có thể chứa attribute tùy chọn **`MethodParameters`**. Attribute này chứa thông tin về mỗi tham số, gồm chỉ mục tên trong *constant pool* (hoặc trường hợp không có tên) và access flags thích hợp. Khi biên dịch bằng `javac -parameters`, compiler thông thường sẽ giữ lại tên tham số trong attribute này để Reflection truy cập.

Cần phân biệt với **`LocalVariableTable`**: đây là thông tin debug có thể được sinh bởi các lựa chọn như `-g`. LocalVariableTable không tương đương với MethodParameters, và **`-g` không thay thế `-parameters`** cho `Parameter.isNamePresent()`. Đừng kết luận một file class đã đủ metadata Reflection chỉ vì debugger nhìn thấy tên biến cục bộ.

| Nguồn thông tin | Chứa gì? | API/đối tượng liên quan | Điểm lưu ý |
| --- | --- | --- | --- |
| Method descriptor | Số lượng và kiểu tham số JVM | `getParameterCount()`, `getParameterTypes()` | Không cần tên tham số source |
| `MethodParameters` (tùy chọn) | Tên và flags của tham số | `getParameters()`, `Parameter.getName()`, `isNamePresent()` | Có thể vắng mặt hợp lệ hoặc có dữ liệu hỏng |
| `LocalVariableTable` (debug) | Biến cục bộ, slot, phạm vi bytecode | Debugger/công cụ phân tích bytecode | Không phải metadata tên tham số Reflection chuẩn |
| `Signature` (khi có) | Thông tin kiểu generic | `getGenericParameterTypes()` và API generic khác | Hỏng Signature có thể sinh lỗi khác, không đồng nhất với `MalformedParametersException` |

**Mô hình:** descriptor nói “tham số thuộc kiểu nào”; MethodParameters bổ sung “tham số tên gì và mang flags nào”. Một method có thể hợp lệ dù thiếu thông tin tên.

## 3. Chính xác khi nào MalformedParametersException có thể xảy ra?

Theo mô tả của API Java, `Executable.getParameters()` có thể ném `MalformedParametersException` khi class file chứa `MethodParameters` được định dạng không đúng.

Các dạng sai phổ biến mà JDK xác định gồm:

1. **Sai số lượng phần tử metadata:** `parameters_count` trong `MethodParameters` không khớp số tham số thực tế của method descriptor.
2. **Tham chiếu constant pool không hợp lệ:** chỉ mục đi ra ngoài phạm vi hoặc trỏ đến mục không thuộc loại `CONSTANT_Utf8` khi cần tên.
3. **Tên tham số không hợp lệ đối với định dạng metadata:** ví dụ chuỗi rỗng `""` hoặc chứa ký tự JVM không cho phép như `.`, `;`, `[`, `/`.
4. **Access flags không được phép:** flags của tham số có bit ngoài nhóm hợp lệ `FINAL`, `SYNTHETIC`, `MANDATED`.

Đừng hiểu điều này thành quy tắc “mọi tên tham số phải duy nhất và là Java identifier chuẩn”. Javadoc của `Executable.getParameters()` nói tên tham số **không nhất thiết duy nhất** hoặc là định danh hợp lệ trong Java source. Điều được kiểm tra ở đây là các ràng buộc của attribute/JDK, không phải việc đặt tên code đẹp.

Một attribute bị hỏng có thể đến từ trình sinh bytecode, trình sửa class, công cụ obfuscation, instrumentation, quá trình transform sau biên dịch hoặc file class bị thay đổi. `javac` bình thường phát sinh metadata đúng với source hợp lệ.

### Khác nhau giữa “không có MethodParameters” và “MethodParameters sai”

```text
MethodParameters không tồn tại
  -> getParameters() thường trả Parameter[] hợp lệ
  -> getName() dùng arg0, arg1, ...
  -> isNamePresent() == false
  -> không tự gây MalformedParametersException

MethodParameters tồn tại nhưng vi phạm quy tắc
  -> getParameters() có thể ném MalformedParametersException
  -> không nên dựa vào việc getName()/isNamePresent() sẽ chạy sau đó
```

Một chương trình thiếu `-parameters` nhưng framework **yêu cầu tên thật** vẫn có thể gặp lỗi cấu hình hoặc binding *riêng của framework*. Lỗi đó cần phân biệt với `MalformedParametersException` do attribute không hợp lệ.

## 4. Ví dụ chạy được: quan sát metadata hợp lệ có và không có -parameters

Chương trình sau minh họa một **đối chứng hợp lệ** để kiểm tra sự khác biệt giữa việc có và thiếu tên tham số. Nó không cố tình tạo class file sai; một ví dụ Java source biên dịch bình thường **không thể tái tạo tự nhiên** lỗi malformed metadata. Mục tiếp theo sẽ trình bày cách tìm class đã bị biến đổi.

Lưu toàn bộ thành file **`ParameterMetadataDemo.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Executable;
import java.lang.reflect.MalformedParametersException;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterMetadataDemo {
    public static class OrderService {
        public OrderService(String region, int retries) {
        }

        public void submit(String orderId, int quantity) {
        }
    }

    private static void inspect(String label, Executable executable) {
        System.out.println(label + ": " + executable.getParameterCount());

        try {
            for (Parameter parameter : executable.getParameters()) {
                System.out.println("  "
                        + parameter.getType().getSimpleName()
                        + " " + parameter.getName()
                        + " | namePresent=" + parameter.isNamePresent());
            }
        } catch (MalformedParametersException ex) {
            System.out.println("  malformed MethodParameters: " + ex.getMessage());
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Method method = OrderService.class.getDeclaredMethod(
                "submit", String.class, int.class);
        Constructor<OrderService> constructor =
                OrderService.class.getDeclaredConstructor(
                        String.class, int.class);

        inspect("method", method);
        inspect("constructor", constructor);
    }
}
```

### Lần chạy A — biên dịch không có -parameters

Dùng Java 17 trở lên:

```bash
javac -encoding UTF-8 ParameterMetadataDemo.java
java ParameterMetadataDemo
```

Kết quả dự kiến từ class vừa biên dịch trong ví dụ:

```text
method: 2
  String arg0 | namePresent=false
  int arg1 | namePresent=false
constructor: 2
  String arg0 | namePresent=false
  int arg1 | namePresent=false
```

Dù không thấy tên `orderId`/`quantity`/`region`/`retries`, `getParameters()` vẫn trả danh sách bình thường. **Đây không phải lỗi metadata malformed.**

### Lần chạy B — biên dịch có -parameters

Biên dịch lại cùng file với cờ giữ tên tham số (javac sẽ ghi đè các class sinh từ file này):

```bash
javac -encoding UTF-8 -parameters ParameterMetadataDemo.java
java ParameterMetadataDemo
```

Kết quả:

```text
method: 2
  String orderId | namePresent=true
  int quantity | namePresent=true
constructor: 2
  String region | namePresent=true
  int retries | namePresent=true
```

Lần này `Parameter.isNamePresent()` là `true` vì `MethodParameters` có dữ liệu tên hợp lệ. Không có ngoại lệ nào được ném trong cả hai lần chạy.

**Lưu ý khi tái hiện:** hãy biên dịch lại đúng file bằng lệnh tương ứng và chạy cùng phiên bản class. Nếu chương trình sử dụng dependency/JAR cũ trên classpath, kết quả có thể phản ánh bytecode khác với file vừa biên dịch.

## 5. Kiểm tra class file bằng javap

`javap` là công cụ đi kèm JDK để xem chữ ký, bytecode và attribute class. Chạy với `-v` (verbose) để thấy thông tin cần chẩn đoán:

```bash
javap -v -p 'ParameterMetadataDemo$OrderService'
```

Lệnh trên áp dụng với Bash hoặc PowerShell, nơi dấu nháy đơn giữ nguyên ký tự `$` trong tên nested class. Trên Windows CMD, dùng dấu nháy kép hoặc escape phù hợp với shell.

Tìm các vùng gần tên phương thức `submit` và constructor, chú ý:

- **Descriptor**, ví dụ `(Ljava/lang/String;I)V`.
- Attribute **MethodParameters** nếu có. Khi đã biên dịch với `-parameters`, tên như `orderId`, `quantity` xuất hiện cạnh flags.
- Trường hợp không có MethodParameters hoàn toàn là hợp lệ và thường tương ứng với lần chạy A.
- Với class thật đang lỗi, đối chiếu **số entry MethodParameters** với **số tham số ở descriptor**, rồi kiểm tra tham chiếu constant pool, tên và flags.

Không chỉ kiểm tra source. Khi có nhiều JAR chứa cùng tên class hoặc class đã qua agent transformer, phải xác định **file class thực sự được classloader nạp**. Một bản `.class` hợp lệ trong thư mục build không chứng minh bản trong JAR đang chạy cũng hợp lệ.

Ví dụ in nguồn tài nguyên của class đang được nạp:

```java
System.out.println(OrderService.class.getProtectionDomain()
        .getCodeSource().getLocation());
```

Đoạn này chỉ là ví dụ để đặt **trong ngữ cảnh class có quyền tham chiếu `OrderService`**. `getCodeSource()` có thể `null` với một số cách nạp/lớp hệ thống; vì vậy code production cần kiểm tra null trước khi dereference. Với class load đặc biệt hoặc mã được transform trong bộ nhớ, vị trí code source cũng có thể không đủ để chứng minh bytecode cuối cùng.

## 6. Quy trình chẩn đoán MalformedParametersException

Khi bắt gặp stack trace, làm theo thứ tự giúp phân biệt lỗi nguồn và lỗi biểu hiện:

**Bước 1 — tìm thao tác Reflection kích hoạt lỗi.** Xem stack trace tại `Executable.getParameters()` và lớp/method nào của ứng dụng hoặc framework gọi nó. Ghi nhận chính xác tên class, tên method/constructor, classloader và JDK runtime. Đừng dừng lại ở dòng lỗi bề ngoài như “không tạo được bean”, “không bind được tham số”, hoặc “không gọi được constructor”.

**Bước 2 — tái hiện tối thiểu trên đúng method.** Nếu đã xác định class và chữ ký, thử:

```java
Method m = SomeType.class.getDeclaredMethod(
        "process", String.class, int.class);
System.out.println(m.getParameterCount());
try {
    for (Parameter p : m.getParameters()) {
        System.out.println(p.getName());
    }
} catch (MalformedParametersException ex) {
    ex.printStackTrace();
}
```

Đây là **mẫu minh họa**: phải thay `SomeType`, `process` và các kiểu tham số bằng class/method có thật. Đặt trong phương thức có khai báo hoặc bắt `NoSuchMethodException`; có đầy đủ import thích hợp. Khi tái hiện, dùng đúng **binary class đã được framework nạp**, không mặc định phiên bản trong IDE là phiên bản lỗi.

**Bước 3 — kiểm tra từng tầng cấu trúc metadata.**

| Câu hỏi chẩn đoán | Công cụ/dữ liệu | Hướng xử lý |
| --- | --- | --- |
| Method descriptor có bao nhiêu tham số? | `javap -v -p`, `getParameterCount()` | Đối chiếu descriptor với MethodParameters |
| MethodParameters có tồn tại không? | `javap -v -p` | Vắng mặt là hợp lệ; xem framework có cần tên thật không |
| Số entry, tên, constant-pool index, flags có hợp lệ? | `javap`/bytecode inspector có kiểm tra class file | Khoanh vùng dữ liệu malformed |
| Class nào/JAR nào thật sự được nạp? | Classloader, code source, dependency tree | Loại bỏ duplicate/stale class hoặc sai classpath |
| File class có qua transformer/obfuscator/shader/agent không? | Cấu hình build, pipeline transform | So sánh bản trước/sau bước biến đổi |
| Một lệnh biên dịch sạch có tái hiện không? | Clean build với cùng JDK và source | Xác định toolchain/transform gây hỏng |

Lưu ý: không phải mọi bytecode tool đều có mức kiểm tra như JVM; một công cụ có thể đọc và in attribute nhưng không tự gắn nhãn “hỏng”. Đối chiếu với quy tắc class file và hành vi Reflection.

**Bước 4 — so bản gốc và bản sau xử lý.** Nếu source Java biên dịch sạch không có lỗi nhưng JAR cuối bị lỗi, so sánh attribute MethodParameters trước/sau các bước weaving, shading, minimization, obfuscation, instrumentation. Các bộ biến đổi phải cập nhật metadata nhất quán khi đổi descriptor/tên và không ghi flags/tên sai.

**Bước 5 — sửa artifact và kiểm tra lại.** Tái sinh class hợp lệ, đồng bộ phiên bản thư viện/công cụ và kiểm tra cả môi trường phát triển lẫn runtime thật. Thêm test gọi `getParameters()` trên những API mà framework phụ thuộc để phát hiện hồi quy trong pipeline.

## 7. Xử lý ngoại lệ đúng tầng và lựa chọn fallback

Vì lỗi nằm trong **metadata của binary**, hướng chính là sửa build/artifact. Ở một số công cụ phân tích có thể cần fallback để tránh sập toàn bộ quá trình quét, nhưng phải ghi nhận rằng tên/thông tin tham số có thể không đáng tin.

Ví dụ chỉ cần **kiểu tham số**, không cần tên:

```java
import java.lang.reflect.Executable;
import java.lang.reflect.MalformedParametersException;

public class MetadataFallback {
    public static void printSignature(Executable executable) {
        System.out.println("Parameter count: " + executable.getParameterCount());
        for (Class<?> type : executable.getParameterTypes()) {
            System.out.println(type.getTypeName());
        }

        try {
            System.out.println("Parameter metadata entries: "
                    + executable.getParameters().length);
        } catch (MalformedParametersException ex) {
            System.err.println("Invalid MethodParameters: " + ex.getMessage());
        }
    }
}
```

Đây là đoạn Java biên dịch được như một class thư viện; chưa có `main`, nên không phải chương trình tự in ra output độc lập. Trường hợp descriptor hợp lệ, `getParameterTypes()` có thể cung cấp kiểu ngay cả khi `getParameters()` lỗi. Nhưng **fallback không khôi phục tên thật**, flags `mandated`/`synthetic`, hoặc bảo đảm logic binding theo tên sẽ đúng.

Khi mapping request, injection hoặc serialization **phụ thuộc tên tham số**, việc âm thầm gán `arg0`/`arg1` hay gán theo vị trí có thể đổi ý nghĩa. Hãy fail rõ ràng, log class/method/artifact và sửa metadata nguồn. Nếu API người dùng thực sự được thiết kế để ánh xạ theo index, chỉ dùng fallback khi đã chứng minh thứ tự và kiểu tham số đủ cho bài toán.

Không dùng `try/catch (Exception ignored)` để che lỗi rồi tiếp tục như thể metadata hợp lệ; cũng không đặt `-parameters` thành giải pháp duy nhất cho mọi `MalformedParametersException`. Cờ này giúp tạo metadata đúng từ source Java bình thường nhưng không tự sửa file class đã bị công cụ khác ghi sai.

## 8. Phân biệt các ngoại lệ Reflection dễ nhầm

| Ngoại lệ | Ngữ cảnh tiêu biểu | Khác biệt |
| --- | --- | --- |
| `MalformedParametersException` | `Executable.getParameters()` đọc MethodParameters sai | Lỗi **metadata mô tả tham số** ở class file |
| `NoSuchMethodException` | `getDeclaredMethod(...)` với tên/kiểu tham số không khớp | Tra cứu method sai; không chứng minh metadata tham số bị hỏng |
| `IllegalArgumentException` | `Method.invoke(...)` truyền đối số không hợp lệ | Lỗi sử dụng API/đối số runtime; có thể phát sinh từ nguyên nhân khác |
| `IllegalAccessException` | Truy cập/invoke method không đủ quyền | Lỗi access control, độc lập với tên tham số |
| `GenericSignatureFormatError` | Parse generic Signature không đúng | Lỗi cú pháp metadata **generic**, không đồng nhất MethodParameters |
| `MalformedParameterizedTypeException` | Kiểu generic không thể được tạo hợp lệ | Lỗi ở mô hình kiểu generic; tên trông giống nhưng bản chất khác |
| `ClassFormatError` | JVM thấy class file sai cấu trúc ở mức load/verify thích hợp | Có thể khiến class không nạp được; khác trường hợp nạp được nhưng `getParameters()` báo malformed attribute |

Lỗi `MalformedParametersException` không nhất thiết xảy ra lúc class được nạp. Tùy loại bất hợp lệ, có thể chỉ lộ ra **khi Reflection cố đọc metadata tham số**. Đừng suy ra “class load thành công thì toàn bộ metadata luôn đúng”.

## 9. Những hiểu nhầm thường gặp

- **“Không có cờ -parameters sẽ gây MalformedParametersException.”** Sai. Với method thông thường, Reflection có tên mặc định `arg0`, `arg1`, `isNamePresent() == false` và không tự ném lỗi chỉ vì attribute vắng mặt.
- **“Bật -g là đủ.”** Sai. Debug `LocalVariableTable` khác attribute `MethodParameters`.
- **“Thấy tên arg0 là metadata hỏng.”** Sai. `arg0` có thể là tên tổng hợp hợp lệ khi không có tên gốc; `Parameter.isNamePresent()` cho biết tên đó có thực sự từ thông tin tên hay không.
- **“MethodParameters có bao nhiêu entry cũng được.”** Sai. Nếu attribute hiện diện thì số lượng phải phù hợp với method descriptor, kể cả tham số implicit/synthetic thực sự ở cấp bytecode.
- **“Chỉ đổi tên source là sửa được class cũ.”** Sai. Phải biên dịch/sinh lại đúng binary được dùng, và kiểm tra mọi transform tiếp theo.
- **“Lỗi trong framework thì chắc chắn framework sai.”** Chưa đủ căn cứ. Framework có thể chỉ là nơi đầu tiên đọc bytecode bị hỏng từ một dependency.
- **“getParameterCount() không lỗi nên getParameters() chắc chắn không lỗi.”** Sai. Hai thao tác không cần đọc cùng một lớp metadata.
- **“Bắt RuntimeException rồi bỏ qua là an toàn.”** Sai. Có thể khiến dữ liệu tên tham số dùng để mapping bị sai lặng lẽ.

## 10. Bài tập thực hành và checklist kiểm chứng

1. Chạy `ParameterMetadataDemo` lần lượt **không có** và **có** `-parameters`. Giải thích vì sao `getParameterCount()` không thay đổi và `isNamePresent()` thay đổi.
2. Dùng `javap -v -p` trên class của `OrderService` trong cả hai bản biên dịch. Chỉ ra descriptor và sự có mặt/vắng mặt của MethodParameters.
3. Giả sử một bytecode transformer thay phương thức từ hai tham số thành một tham số nhưng giữ MethodParameters có hai entry. Dự đoán khi nào `MalformedParametersException` có thể xuất hiện và cách xác nhận.
4. Nếu server báo lỗi lúc binding tên tham số nhưng `getParameters()` chạy được và `isNamePresent()` là `false`, cần xem lại gì trong compiler/framework?
5. Nếu cùng source chạy đúng ở IDE nhưng lỗi trong fat JAR, xác định lớp bước nào trong build/deployment cần so sánh.

**Checklist khi debug production:** ghi đầy đủ `exception + stack trace → class/method descriptor → binary/classloader thực tế → MethodParameters trong artifact → toolchain và từng bước biến đổi → clean rebuild → test đọc lại getParameters()`.

**Kết quả cần đạt:** phân biệt được dữ liệu tham số **bị thiếu hợp lệ** với dữ liệu **hiện diện nhưng malformed**, hiểu vì sao `Executable.getParameters()` có thể ném unchecked exception, và biết truy ngược artifact gây lỗi để sửa nguyên nhân.

### Tài liệu tham khảo

- [Javadoc Java 21: Executable.getParameters()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Executable.html#getParameters())
- [Javadoc Java 21: MalformedParametersException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/MalformedParametersException.html)
- [Tài liệu javac: tùy chọn -parameters](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
