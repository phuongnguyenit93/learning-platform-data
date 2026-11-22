# GenericSignatureFormatError, TypeNotPresentException và MalformedParameterizedTypeException khi dùng Java Reflection

## 1. Vì sao reflection đọc generic lại phát sinh lỗi?

Khi chương trình Java biên dịch các kiểu như `List<String>` hoặc `class Child extends Parent<Long>`, JVM chủ yếu làm việc với **kiểu đã xóa (erasure)**, còn thông tin tham số kiểu được compiler lưu trong thuộc tính **`Signature`** của class file khi cần. Các API `java.lang.reflect` đọc metadata này để tạo cây `Type` (`Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`, `GenericArrayType`).

Ví dụ, trường `List<String> names` thường có hai lớp thông tin:

| Lớp thông tin | Diễn đạt | Truy cập |
| --- | --- | --- |
| Descriptor sau erasure | `Ljava/util/List;` | `Field.getType()` trả `List.class` |
| Generic signature | `Ljava/util/List<Ljava/lang/String;>;` | `Field.getGenericType()` trả một `ParameterizedType` chứa `String` |

**Hệ quả:** Một class có thể được tải, một field có thể được tìm thấy và kiểu raw `List` có thể được đọc, nhưng thao tác **phân tích hoặc phân giải generic signature** vẫn thất bại. Không nên coi `Class.forName(...)` thành công là bằng chứng mọi metadata generic đều hợp lệ.

Ba lỗi của bài là:

- `java.lang.reflect.GenericSignatureFormatError`: biểu diễn `Signature` **sai cú pháp** theo đặc tả JVM.
- `java.lang.TypeNotPresentException`: metadata cần **một kiểu không thể phân giải**, thường do thiếu class/dependency khi chạy.
- `java.lang.reflect.MalformedParameterizedTypeException`: cấu trúc tham số hóa **sai về ngữ nghĩa**, dù chuỗi signature có thể đúng cú pháp.

Chúng thường xuất hiện khi quét thư viện, ORM, serialization, dependency injection, annotation processor/runtime scanner, proxy/bridge metadata, plugin hoặc class do công cụ bytecode sinh/biến đổi. Tuy nhiên đây **không phải** ba lỗi mà mọi reflection call đều ném; phụ thuộc API và phần metadata mà nó cần phân giải.

## 2. Bảng phân biệt nhanh ba lỗi

| Lỗi | Quan hệ kế thừa | Tình huống đặc trưng | Hướng kiểm tra |
| --- | --- | --- | --- |
| `GenericSignatureFormatError` | `Error → LinkageError → ClassFormatError → GenericSignatureFormatError` | Thuộc tính `Signature` không tuân thủ grammar, ví dụ thiếu dấu kết thúc | Kiểm tra class file, bytecode generator/transformer, phiên bản artifact |
| `TypeNotPresentException` | `RuntimeException` | `Signature` đề cập `com.example.Missing` nhưng class loader không tìm thấy định nghĩa | Đọc `typeName()`, `getCause()` và dependency/classpath/module path |
| `MalformedParameterizedTypeException` | `RuntimeException` | Signature có tham số hóa nhưng không thể tạo `ParameterizedType` hợp lệ, ví dụ số type arguments sai | Kiểm tra số lượng/owner type của tham số generic, version mismatch và bytecode đã biến đổi |

**Ranh giới quan trọng:** `GenericSignatureFormatError` là một `Error`, không phải `Exception`; `catch (RuntimeException e)` không bắt được nó. Hai lỗi còn lại đều là unchecked `RuntimeException`. Không nên dùng `catch (Throwable)` bừa bãi và tiếp tục khởi tạo hệ thống sau khi phát hiện class metadata hỏng.

### 2.1. `GenericSignatureFormatError` — lỗi cú pháp của Signature

Theo Java API, lỗi xảy ra khi một reflection method cần diễn giải một thuộc tính `Signature` không tuân thủ cú pháp đặc tả class file. Ví dụ minh họa **chỉ là chuỗi trong class file, không phải mã Java hợp lệ**:

~~~text
Hợp lệ:
Ljava/util/List<Ljava/lang/String;>;

Sai cú pháp (thiếu dấu kết thúc cho type arguments và class type):
Ljava/util/List<Ljava/lang/String;
~~~

Một `Signature` sai có thể được viết bởi bytecode generator, instrumentation/weaver, obfuscator hoặc quá trình sửa class file. Compiler `javac` bình thường không xuất ra kiểu lỗi này từ mã nguồn Java hợp lệ. Đừng tạo ví dụ bằng cách viết `List<String, Integer>` trong source rồi mong chạy đến reflection: source sẽ bị compiler từ chối trước.

Vì thuộc tính `Signature` là metadata bổ sung, lỗi có thể chỉ lộ ra khi API parse generic được gọi. Mặt khác, class file hỏng nghiêm trọng có thể bị JVM từ chối sớm bằng lỗi khác; không được bảo đảm mọi trường hợp sai bytecode đều đợi đến `getGenericType()`.

### 2.2. `TypeNotPresentException` — không tìm thấy kiểu khi phân giải metadata

Đây là exception unchecked thuộc **`java.lang`**. API `typeName()` trả tên kiểu không có định nghĩa, và `getCause()` có thể chứa nguyên nhân, ví dụ `ClassNotFoundException`; cause được phép `null`. Có thể thấy lỗi khi reflection đọc generic signature, hoặc khi đọc annotation runtime chứa giá trị `Class` không phân giải được.

Ví dụ: source ban đầu có `List<demo.Absent>`; sau khi đóng gói, `demo.Absent` biến mất nhưng `Holder.class` vẫn giữ generic `Signature`. Field raw type vẫn là `java.util.List`; lúc `getGenericType()` phân giải tham số kiểu, lỗi xuất hiện.

Đừng đồng nhất với:

- `ClassNotFoundException`: checked exception thường gặp khi chủ động tìm class theo tên bằng `Class.forName(...)` / `ClassLoader.loadClass(...)`; cũng có thể nằm trong `cause`.
- `NoClassDefFoundError`: lỗi liên kết/tải khi JVM cần một định nghĩa class tại runtime; không mặc định biến thành `TypeNotPresentException`.
- `NoSuchMethodException` / `NoSuchFieldException`: tra cứu thành viên không tồn tại, không nói rằng `Signature` generic bị lỗi.

### 2.3. `MalformedParameterizedTypeException` — sai cấu trúc type arguments

Đây là unchecked `RuntimeException`: reflection cần tạo một kiểu tham số hóa nhưng biểu diễn đó **không hợp lệ về ngữ nghĩa**. Ví dụ tiêu biểu trong Java API: số lượng đối số kiểu không phù hợp với khai báo của raw type.

Ví dụ minh họa bằng chuỗi signature (không phải chương trình Java chạy được):

~~~text
Đúng cú pháp, và hợp lệ với java.util.List<E>:
Ljava/util/List<Ljava/lang/String;>;

Đúng dạng cú pháp tham số hóa nhưng sai số lượng đối số cho List<E>:
Ljava/util/List<Ljava/lang/String;Ljava/lang/Integer;>;
~~~

`List` chỉ khai báo **một** biến kiểu `E`; hai type arguments không thể tương ứng với khai báo này. Đây là lỗi khác hẳn việc thiếu ký tự trong grammar. Các vấn đề metadata owner/nested parameterization không phù hợp cũng cần được xem xét, nhưng không nên khẳng định mọi bound generic bị vi phạm đều chắc chắn ném exception này: cách kiểm tra cụ thể phụ thuộc API và biểu diễn được tạo.

## 3. API nào có thể phát hiện các lỗi này?

Các method truy vấn **generic metadata** trong Java SE 21 thường công bố ba lỗi trên trong JavaDoc, tùy thuộc vào signature cụ thể:

| API | Metadata đang phân giải |
| --- | --- |
| `Class.getGenericSuperclass()` | Superclass dạng `Parent<String>` |
| `Class.getGenericInterfaces()` | Interface dạng `Comparable<MyType>` |
| `Field.getGenericType()` | Kiểu khai báo của field như `Map<String, User>` |
| `Method.getGenericReturnType()` | Kiểu trả về khai báo như `List<Response>` |
| `Method.getGenericParameterTypes()` | Các tham số như `Optional<Request>` |
| `Constructor/Method.getGenericExceptionTypes()` | Kiểu trong mệnh đề `throws` của `Executable` |
| `Class.getTypeParameters()` / `Method.getTypeParameters()` | Khai báo biến kiểu và các giới hạn (bounds) |

Một số phép truy vấn có thể tạo `Type` lazily; lỗi có thể phát sinh khi truy cập sâu hơn vào `ParameterizedType.getActualTypeArguments()`, `TypeVariable.getBounds()` hoặc kiểu owner. Do đó, khi chẩn đoán, ghi lại **phương thức reflection chính xác** và **thời điểm chạm vào cây Type**, không chỉ tên class đang scan.

Các API trả kiểu sau erasure như `Field.getType()` hoặc `Method.getReturnType()` không có cùng nghĩa với API generic; thành công ở API raw không chứng minh Signature hay dependencies của type arguments đầy đủ.

## 4. Ví dụ Java 17+: tái hiện TypeNotPresentException thật

Ví dụ dưới đây tạo một class có field `List<Absent>`, biên dịch đầy đủ, sau đó **cố ý xóa một class trong thư mục thử nghiệm**. Metadata generic còn đề cập `demo.Absent`, nhưng class không còn trong classpath. Lưu ý: chỉ xóa file thử nghiệm được tạo trong thư mục riêng; không xóa class của dự án đang chạy.

Tạo ba tệp đúng tên:

**`src/demo/Absent.java`**

~~~java
package demo;

public class Absent {}
~~~

**`src/demo/Holder.java`**

~~~java
package demo;

import java.util.List;

public class Holder {
    public List<Absent> values;
}
~~~

**`src/GenericDiagnosticDemo.java`**

~~~java
import java.lang.reflect.Field;

public class GenericDiagnosticDemo {
    public static void main(String[] args) throws Exception {
        Field field = Class.forName("demo.Holder")
                .getDeclaredField("values");

        System.out.println("Erased field type: "
                + field.getType().getTypeName());

        try {
            System.out.println("Generic type: "
                    + field.getGenericType().getTypeName());
        } catch (TypeNotPresentException e) {
            System.out.println("Missing generic type: " + e.typeName());
            Throwable cause = e.getCause();
            System.out.println("Cause class: "
                    + (cause == null ? "none" : cause.getClass().getName()));
        }
    }
}
~~~

Trong một thư mục thử nghiệm mới, tạo `src/demo` và `classes`, đặt các file vào đường dẫn trên rồi thực hiện:

~~~bash
javac --release 17 -d classes src/demo/Absent.java src/demo/Holder.java src/GenericDiagnosticDemo.java
rm classes/demo/Absent.class
java -cp classes GenericDiagnosticDemo
~~~

Trên Windows PowerShell, thay dòng `rm` bằng `Remove-Item classes/demo/Absent.class`; các lệnh `javac` và `java` vẫn như trên.

**Stdout** của tình huống này trên JDK 17+:

~~~text
Erased field type: java.util.List
Missing generic type: demo.Absent
Cause class: java.lang.ClassNotFoundException
~~~

Điều đáng học: `Class.forName("demo.Holder")`, `getDeclaredField("values")` và `field.getType()` vẫn chạy được. `field.getGenericType()` mới buộc reflection phân giải `Absent` trong generic signature và ném `TypeNotPresentException`. Nếu bạn giữ `Absent.class`, lời gọi này trả `java.util.List<demo.Absent>` bình thường.

Khi phân tích file đã biên dịch, dùng:

~~~bash
javap -v -p -classpath classes demo.Holder
~~~

Trong output của `javap`, tìm trường `values` và dòng `Signature` để thấy metadata giữ tham chiếu tới `demo.Absent`. Đây là lệnh chẩn đoán class file, output dài và phụ thuộc bản JDK nên không cần so khớp toàn bộ output.

## 5. Quy trình chẩn đoán trong ứng dụng thực tế

Khi framework scan generic type của class từ thư viện khác, thực hiện theo thứ tự:

1. **Ghi rõ vị trí lỗi.** Class, tên field/method, API gây lỗi (ví dụ `Field.getGenericType()`), exception đầy đủ, `typeName()` nếu là `TypeNotPresentException`, cause và stack trace. Không log dữ liệu nghiệp vụ nhạy cảm.
2. **Kiểm tra nguồn class đang thực sự được tải.** Xem `clazz.getProtectionDomain().getCodeSource()` khi có giá trị và class loader/module liên quan; kiểm tra có hai phiên bản JAR của cùng thư viện hoặc class trùng ở nhiều class loader không.
3. **Đối chiếu runtime dependencies.** Với `TypeNotPresentException`, tìm class thiếu trong artifact và dependency tree; kiểm tra shading/relocation, optional dependency, đóng gói module và phiên bản API–implementation.
4. **Đọc class file.** Dùng `javap -v -p`, xem `Signature` và raw descriptor. Với `GenericSignatureFormatError`, kiểm tra grammar và công cụ sinh/sửa bytecode. Với `MalformedParameterizedTypeException`, so arity và cấu trúc type arguments với khai báo generic thực tế của raw type.
5. **Tái hiện trong classpath tối giản.** Chạy cùng JDK và cùng cặp JAR đang triển khai; có thể thử build sạch, nhưng không thay class file sản xuất trực tiếp khi đang phân tích. Tìm bước build/weaving/obfuscation thay đổi `Signature`.
6. **Khắc phục tại nguồn.** Bổ sung dependency chính xác, đồng bộ binary versions, sửa bytecode transformer/generator, hoặc loại bỏ artifact hỏng rồi build lại; không dùng `--add-opens` như cách chữa mặc định vì đây thường không phải lỗi quyền truy cập reflection.

### Một mẫu xử lý lỗi có chủ đích

Đoạn sau là **phần thân mẫu** của một hàm đọc generic field type, không phải một chương trình độc lập:

~~~java
try {
    return field.getGenericType();
} catch (TypeNotPresentException ex) {
    // typeName() cho biết kiểu thiếu; cause có thể null.
    throw new IllegalStateException(
            "Missing generic type " + ex.typeName()
            + " on " + field, ex);
} catch (java.lang.reflect.MalformedParameterizedTypeException ex) {
    throw new IllegalStateException(
            "Invalid parameterized type on " + field, ex);
} catch (java.lang.reflect.GenericSignatureFormatError err) {
    // Metadata class file bị hỏng: báo lỗi rõ ràng rồi dừng.
    throw new IllegalStateException(
            "Invalid generic signature on " + field, err);
}
~~~

Trong framework có vòng scan lớn, có thể ghi chẩn đoán theo từng class để biết module nào bị ảnh hưởng. Tuy nhiên, chỉ **fallback từ `getGenericType()` sang `getType()`** khi nghiệp vụ cho phép mất toàn bộ type arguments; ví dụ, serializer cần kiểu `List<User>` mà chỉ còn `List.class` thì tiếp tục đoán `User` sẽ gây lỗi dữ liệu.

**Lưu ý về catch `Error`:** việc bắt riêng `GenericSignatureFormatError` có thể hữu ích ở ranh giới chẩn đoán để bổ sung ngữ cảnh, nhưng đừng bắt mọi `Error` rồi cho hệ thống tiếp tục. Lỗi Signature cho thấy artifact hoặc metadata có vấn đề cần sửa tại nguồn.

## 6. Những hiểu nhầm cần tránh

| Nhận định dễ sai | Điều đúng |
| --- | --- |
| “`Class.forName` thành công thì metadata generic chắc chắn đọc được.” | Generic `Signature` có thể được phân tích/phân giải về sau, lúc gọi API tương ứng. |
| “Cả ba đều là exception từ `java.lang.reflect`.” | `TypeNotPresentException` thuộc `java.lang`; `GenericSignatureFormatError` là `Error`. |
| “`GenericSignatureFormatError` giống `MalformedParameterizedTypeException`.” | Cái trước sai grammar; cái sau có thể đúng grammar nhưng sai ngữ nghĩa của kiểu tham số hóa. |
| “`TypeNotPresentException` luôn có cause.” | `getCause()` có thể `null`; nên đọc `typeName()` trước. |
| “Xóa một class trong `List<Absent>` luôn làm `Holder` không load được.” | Khi `Absent` chỉ hiện diện trong generic signature, raw field descriptor có thể vẫn hợp lệ; lỗi chỉ xuất hiện khi đọc metadata generic. |
| “`ClassNotFoundException`, `NoClassDefFoundError` và `TypeNotPresentException` giống nhau.” | Chúng có hierarchy, thời điểm và ngữ cảnh phát sinh khác nhau. |
| “Có thể sửa generic metadata bằng `setAccessible(true)`.” | `setAccessible` tác động kiểm tra truy cập member, không sửa classpath hay bytecode Signature. |
| “Bất kỳ mã Java sai generic nào cũng tạo ra lỗi runtime này.” | `javac` chặn phần lớn source sai generic từ lúc compile; lỗi runtime này thường đến từ metadata nhị phân hoặc môi trường tải. |

## 7. Tự kiểm tra kiến thức

1. Với field `List<Missing>`, vì sao `getType()` có thể trả về `List.class` còn `getGenericType()` lại thất bại?
2. Phân biệt một `Signature` thiếu dấu kết thúc với chữ ký `List<String, Integer>` bị ghi vào class file của một raw type chỉ có một type parameter.
3. Khi bắt `TypeNotPresentException`, hai thông tin nào giúp xác định dependency bị thiếu?
4. Vì sao `catch (RuntimeException)` không chặn `GenericSignatureFormatError`?
5. Trường hợp nào dùng fallback sang kiểu raw an toàn, và khi nào phải dừng để tránh deserialize dữ liệu sai?

### Tài liệu Java API chính thức

- Java SE 21, `GenericSignatureFormatError`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/GenericSignatureFormatError.html
- Java SE 21, `TypeNotPresentException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/TypeNotPresentException.html
- Java SE 21, `MalformedParameterizedTypeException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/MalformedParameterizedTypeException.html
- Java SE 21, `Field`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html
- Java SE 21, `Class`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- JVM Specification §4.7.9.1 (Signatures): https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.9.1