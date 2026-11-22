# Không dùng tên tham số Reflection như hợp đồng ổn định khi build không bảo đảm metadata

## 1. Vấn đề: tên trong mã Java chưa chắc tồn tại ở runtime

Giả sử một phương thức được viết trong source code:

```java
public void send(String recipient, int retryCount) {
    // Xử lý gửi dữ liệu.
}
```

Hai tên `recipient` và `retryCount` giúp người viết code hiểu ý nghĩa đối số. Nhưng sau khi biên dịch thành `.class`, **Java Reflection không luôn lấy lại được hai tên này**. Điều đó phụ thuộc class file thực sự chứa metadata về tên formal parameter hay không.

Nếu một framework tự suy luận khóa JSON, query parameter, tên biến CLI hoặc tên trường cấu hình từ `Parameter.getName()`, chương trình có thể đột ngột xuất hiện những khóa như `arg0`, `arg1` khi dùng artifact được biên dịch với tùy chọn khác.

**Nguyên tắc cốt lõi:** *Không dùng tên tham số Java được đọc bằng Reflection làm hợp đồng API ổn định nếu quy trình build không bảo đảm metadata; ngay cả khi metadata hiện diện, sự hiện diện của tên chưa tự biến tên source thành một hợp đồng được phiên bản hóa.*

Bài học này thuộc chủ đề **tham số executable**: các đối tượng `Method` và `Constructor` đều kế thừa `java.lang.reflect.Executable`; chúng cung cấp `getParameters()`, trả về các đối tượng `java.lang.reflect.Parameter` để đọc tên, kiểu và thuộc tính từng formal parameter.

## 2. Tách metadata có tên và hợp đồng bên ngoài

`Parameter.getName()` luôn cho một chuỗi, kể cả tên tổng hợp `arg0`, `arg1` khi thiếu tên trong `MethodParameters`. `Parameter.isNamePresent()` mới xác định class file có cung cấp tên cho **tham số này** hay không.

`getType()` và `getParameterizedType()` đọc mô tả kiểu bằng các metadata khác; chữ ký lookup của JVM không dựa vào tên formal parameter. Kể cả khi `isNamePresent()` là `true`, một lần đổi `recipient` thành `target` có thể giữ nguyên chữ ký Java/JVM mà lại đổi tên do framework suy ra cho request.

Vì vậy có hai kiểm tra độc lập: **có metadata tên trong artifact không?** và **tên ấy có được công bố, quản trị và kiểm thử như một hợp đồng bên ngoài không?**

## 3. Vì sao hai bản build có thể có hợp đồng khác nhau?

Với `javac`, tùy chọn biên dịch `-parameters` ghi formal parameter names vào `MethodParameters`; tùy chọn `-g` phục vụ debug information và không thay thế cờ này cho Core Reflection. CI, JAR dependency, obfuscator và bytecode transformer có thể tạo artifact giữ metadata khác bản chạy trong IDE.

Kiểm tra `javap -v -p` trên **chính class file hoặc JAR được phát hành**, rồi kiểm tra `isNamePresent()` trong test. Metadata về generic types và runtime annotations có cơ chế độc lập; không nên lấy sự có mặt của chúng làm bằng chứng rằng tên tham số cũng được giữ.

## 4. Thí nghiệm Java 17: tên source thay đổi, tên external vẫn ổn định

Bài toán khác với việc chỉ in `argN`: ta thử một annotation xác định tên contract độc lập với tên biến Java. Tạo file `StableContractDemo.java`:

```java
import java.lang.annotation.*;
import java.lang.reflect.*;

public class StableContractDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface ExternalName {
        String value();
    }

    static class Endpoint {
        public void send(@ExternalName("recipient") String target,
                         @ExternalName("retryCount") int attempts) {}
    }

    public static void main(String[] args) throws Exception {
        Method method = Endpoint.class.getDeclaredMethod(
                "send", String.class, int.class);
        for (Parameter parameter : method.getParameters()) {
            ExternalName contract = parameter.getAnnotation(ExternalName.class);
            System.out.println("name=" + parameter.getName()
                    + ", present=" + parameter.isNamePresent()
                    + ", external=" + contract.value());
        }
    }
}
```

Biên dịch và chạy hai bản tách biệt:

```bash
javac --release 17 -d plain StableContractDemo.java
javac --release 17 -parameters -d named StableContractDemo.java
java -cp plain StableContractDemo
java -cp named StableContractDemo
```

Bản `plain` in:

```text
name=arg0, present=false, external=recipient
name=arg1, present=false, external=retryCount
```

Bản `named` in:

```text
name=target, present=true, external=recipient
name=attempts, present=true, external=retryCount
```

Hai bản build khác nhau ở tên phản chiếu, nhưng `external` không đổi vì annotation có `@Retention(RUNTIME)` và chứa tên công bố trực tiếp. Tên `target`/`attempts` có thể được refactor mà contract `recipient`/`retryCount` vẫn giữ nguyên khi annotation không đổi. Đây là cách biểu diễn thiết kế: annotation tùy chỉnh **không tự thực hiện binding**, framework phải chủ động đọc và sử dụng tên đã khai báo.

## 5. Vì sao đây là rủi ro với hợp đồng API?

Một **hợp đồng ổn định** là những gì người gọi bên ngoài có quyền trông đợi qua các bản phát hành, chẳng hạn tên query parameter `recipient`, khóa JSON `retryCount`, tên command-line option, field trong configuration hoặc tên trường được framework bind từ request.

Tên biến trong Java source không tự động là một hợp đồng như vậy:

- **Môi trường build khác nhau:** máy phát triển, CI, module phụ hoặc project consumer có thể cấu hình `javac` khác nhau. Có bản class có `MethodParameters`, bản khác không.
- **Dependency bên ngoài:** bạn không kiểm soát tùy chọn compile của thư viện bên thứ ba; `isNamePresent()` có thể trả `false`.
- **Công cụ sau biên dịch:** obfuscator, bytecode transformer, minifier hoặc quá trình đóng gói có thể đổi, loại bỏ hoặc tái tạo metadata.
- **Refactor hợp lệ về mặt Java:** đổi tên formal parameter từ `recipient` thành `destination` thường **không đổi JVM method descriptor**; lời gọi Java dựa trên vị trí và kiểu vẫn hợp lệ, nhưng một framework tự rút khóa API từ `getName()` có thể đổi tên khóa từ bên ngoài.
- **Tên tổng hợp trông hợp lệ:** `arg0`, `arg1` là chuỗi không rỗng, dễ bị framework dùng nhầm làm khóa thật nếu không kiểm tra `isNamePresent()`.
- **Thông tin vị trí khác ý nghĩa:** chỉ số tham số là một phần của chữ ký thực thi, nhưng không nói tự thân tham số dùng cho nghiệp vụ gì. Đổi thứ tự/số tham số cũng thay đổi hợp đồng mà adapter của bạn cần quản lý.

Ví dụ framework tự động đặt khóa map:

```java
for (Parameter parameter : method.getParameters()) {
    String externalKey = parameter.getName();
    // Rủi ro: externalKey có thể là arg0/arg1.
}
```

Đây là mảnh mã minh họa, giả định đã có `Method method` và import `Parameter`. Trong build thiếu metadata, API vốn muốn công bố `recipient` và `retryCount` có thể đột ngột công bố `arg0` và `arg1` — vi phạm hợp đồng bên ngoài mà không cần bất kỳ thay đổi logic Java nào.

**Ngay cả khi `isNamePresent() == true`, tên đó vẫn có thể bị đổi giữa hai bản class**. Chỉ nên coi nó là giao diện bên ngoài khi dự án **đã công bố** sự ổn định của tên, build được kiểm soát và kiểm thử tương thích có mặt. Metadata chỉ là điều kiện cần để quan sát đúng tên, không phải bằng chứng tự động về tính bất biến nghiệp vụ.

## 6. Chiến lược thiết kế an toàn hơn

### A. Khai báo tên giao tiếp bên ngoài một cách tường minh

Với endpoint, message consumer, CLI, serializer hoặc dependency injection, nên xác định những khóa bên ngoài bằng cấu hình/schema hoặc annotation **có giá trị rõ ràng**, thay vì ngầm rút từ tên biến Java.

Ví dụ giả định một framework cung cấp annotation lưu tên bên ngoài:

```java
void send(
        @RequestKey("recipient") String target,
        @RequestKey("retryCount") int attempts
) {
    // Hai tên external không phụ thuộc tên target/attempts trong source.
}
```

Đây là **mã minh họa, không độc lập**, `@RequestKey` là annotation ví dụ và phải được định nghĩa hoặc thay bằng annotation thật của framework đang dùng. Điểm quan trọng là tên bên ngoài `recipient` và `retryCount` đã được khai báo **trực tiếp**, không còn bị suy ra từ `target` hay `attempts`.

Nếu tự xây framework, annotation phải có retention phù hợp để runtime đọc được, chẳng hạn `@Retention(RetentionPolicy.RUNTIME)` trên annotation parameter. Annotation không có runtime retention sẽ không trở thành metadata runtime hợp lệ chỉ vì đã có `-parameters`.

Những lựa chọn tương đương:

- Schema JSON/OpenAPI/protobuf hoặc contract file định nghĩa khóa ở tầng giao tiếp.
- Một mapping tường minh giữa **vị trí/kiểu formal parameter** và tên external được duy trì/test.
- Một annotation runtime với tên external cố định, có versioning và validation.
- Các interface/DTO có property public được quản trị bằng hợp đồng phiên bản hóa thay vì phụ thuộc vào tên local variable.

### B. Nếu ứng dụng thực sự muốn suy tên, kiểm tra và thất bại rõ ràng

Có những thư viện chủ động xem tên tham số Java là một tiện ích — ví dụ framework nội bộ cần tự bind đối số theo tên. Khi đó hãy coi metadata hiện diện là **precondition bắt buộc** và kiểm tra nó lúc khởi động, không chấp nhận tên tổng hợp trong im lặng:

```java
static String[] requireParameterNames(Executable executable) {
    Parameter[] parameters = executable.getParameters();
    String[] names = new String[parameters.length];

    for (int i = 0; i < parameters.length; i++) {
        if (!parameters[i].isNamePresent()) {
            throw new IllegalStateException(
                    "Missing parameter name metadata for "
                    + executable + " parameter #" + i
                    + ". Compile with -parameters."
            );
        }
        names[i] = parameters[i].getName();
    }
    return names;
}
```

Đoạn trên là **phương thức minh họa**, giả định đã import `Executable` và `Parameter`; đặt vào class Java thích hợp để sử dụng. Nó chỉ giải quyết **thiếu metadata**, chứ **không bảo đảm** rằng tên được hiện diện sẽ ổn định qua thay đổi source/build. Cần thêm kiểm thử và quy ước versioning nếu tên trở thành API.

Việc kiểm tra có tên phải thực hiện **từng `Parameter`**, không chỉ nhìn một phần tử rồi giả định tất cả có dữ liệu đúng. Với executable đặc biệt hoặc class files từ các công cụ khác nhau, cần đặc biệt cẩn thận về nguồn gốc từng parameter.

### C. Khi chỉ cần thao tác phương thức, đừng hỏi tên tham số

Nếu mục tiêu là tìm và gọi method bằng Reflection, hãy dùng:

```java
Method method = type.getDeclaredMethod(
        "send", String.class, int.class
);
method.invoke(receiver, "alice", 3);
```

Đây là mã minh họa, giả định `type`, `receiver` tương thích và đã import `Method`; caller phải xử lý các ngoại lệ Reflection. **Tra cứu và gọi dựa trên thứ tự cùng kiểu tham số**, không cần tên `recipient`/`retryCount` có được lưu hay không.

Với công cụ cần biết kiểu generic, có `getGenericParameterTypes()` và `Parameter.getParameterizedType()`; với chú thích tham số có `getParameterAnnotations()` hoặc `Parameter.getAnnotation()`. Những metadata đó có hợp đồng riêng và không nên bị nhập làm một với tên.

## 7. Quy tắc build và kiểm thử contract

Nếu hệ thống chủ động sử dụng tên formal parameter làm API, hãy bật `-parameters` trên **mọi module định nghĩa executable cần đọc tên**, kiểm tra artifact sau tối ưu/đóng gói và kiểm thử công khai hóa tên. Việc bật cờ trong ứng dụng gọi không thêm metadata vào JAR của dependency đã biên dịch sẵn.

Một kiểm thử tốt cần hai loại assertion: `isNamePresent()` cho tham số mà framework dựa vào và **tên external được mong đợi** của endpoint/schema qua các phiên bản. Chỉ kiểm tra metadata present chưa phát hiện được thay đổi contract do refactor tên source. Nếu tên external nằm trong annotation/schema, test phải so giá trị annotation/schema đó và behavior binding thật.

## 8. Cẩn trọng với executable đặc biệt

Constructor của non-static inner class hoặc enum, cùng các executable compiler-generated, có thể chứa tham số implicit/synthetic ngoài source. Khi xây binder tổng quát, kiểm tra `getParameters()`, `getParameterTypes()`, `isImplicit()` và `isSynthetic()` theo artifact thay vì giả định index 0 luôn là tham số nghiệp vụ. Những cờ này giúp mô tả nguồn gốc tham số; chúng **không bảo đảm** tên được công bố ổn định.

## 9. Lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| `getName()` dùng ngay làm HTTP/JSON key | Thiếu metadata có thể xuất hiện `argN` | Annotation/schema nêu tên hoặc fail fast khi thiếu tên |
| `isNamePresent=true` được xem là bảo đảm ổn định | Rename source vẫn đổi contract | Kiểm thử tên API public và quản lý thay đổi phiên bản |
| Bật `-parameters` chỉ ở module consumer | Dependency đã build không được bổ sung metadata | Cấu hình compiler ở module khai báo executable |
| Fallback âm thầm sang `argN` | Lỗi binding khó phát hiện | Báo lỗi cấu hình có method và parameter index |
| Tên annotation được đọc nhưng binder không sử dụng | API vẫn bind theo tên Java | Viết/test code mapping dựa trên giá trị annotation |

## 10. Câu hỏi tự kiểm tra

1. Một tham số source tên `recipient` nhưng class file thiếu `MethodParameters`. `getName()` có nhất thiết trả `recipient` không? **Không.** Có thể là `arg0`; `isNamePresent()` là `false`.
2. Nếu `getName()` trả `arg0`, có nên kết luận chắc chắn metadata bị thiếu chỉ dựa vào chuỗi không? **Không.** Dùng `isNamePresent()`, vì không kiểm tra thông qua hình dạng tên.
3. Bật tùy chọn nào khi dùng `javac` để lưu formal parameter names? **`-parameters`**.
4. `javac -g` có phải bảo đảm `Parameter.isNamePresent() == true` không? **Không.** Debug information và `MethodParameters` là các khái niệm khác.
5. Vì sao framework tạo API key từ `getName()` có nguy cơ? **Thiếu/đổi metadata, obfuscation hoặc refactor** có thể đổi key.
6. Nếu `isNamePresent()` là `true`, tên đã trở thành public API ổn định chưa? **Chưa.** Phải quản trị tên và tương thích ở mức thiết kế/version.
7. `Executable.getParameters()` sử dụng cho cả method và constructor không? **Có.** Cả `Method` và `Constructor` đều kế thừa `Executable`.
8. `getDeclaredMethod("send", String.class, int.class)` có cần lưu tên `recipient` và `retryCount` không? **Không.** Tra cứu dùng tên method và formal parameter types.

## 11. Tài liệu chính thức

- [Oracle Java SE 21 — `java.lang.reflect.Parameter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html): hợp đồng `getName()`, `isNamePresent()`, `isImplicit()`, `isSynthetic()`.
- [Oracle Java SE 21 — `java.lang.reflect.Executable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Executable.html): truy vấn `getParameters()`, số tham số, kiểu và annotation của method/constructor.
- [Oracle Java SE 21 — công cụ `javac`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): ý nghĩa tùy chọn `-parameters` và các tùy chọn debug.
- [The Java Virtual Machine Specification SE 21 — §4.7.24 `MethodParameters`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.24): cấu trúc class file dành cho metadata formal parameters.
- [Dev.java — Invoking Methods](https://dev.java/learn/reflection/methods/): ví dụ và lưu ý chính thức về Reflection, tên formal parameter và compiler option.

**Ghi nhớ:** `getName()` có thể trả `arg0`/`arg1` nếu thiếu metadata; `isNamePresent()` xác nhận **có tên trong class file**, không xác nhận **tên ấy là hợp đồng ổn định**. Muốn công bố tên ra bên ngoài, hãy dùng schema/annotation tường minh hoặc kiểm soát build `-parameters` cộng với kiểm thử và chính sách tương thích.