# Giá trị trả về của `process` và quy tắc nhận xử lý annotation trong Java

## 1. Mục tiêu: hiểu `true` và `false` trong annotation processing

Trong Java, **annotation processor** là chương trình được compiler hoặc công cụ build gọi để kiểm tra, phân tích hoặc tạo tệp dựa trên annotation ở thời điểm biên dịch. JSR 269 cung cấp API `javax.annotation.processing.Processor`; cách triển khai thông dụng là kế thừa `AbstractProcessor`.

Một phương thức trung tâm:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    // Kiểm tra những annotation type được giao trong round này.
    return false;
}
```

Giá trị boolean ở đây **không** trả lời “xử lý có thành công hay không”. Nó trả lời câu hỏi:

> “Processor này có **claim** (nhận quyền xử lý) những *annotation types* được giao ở lượt gọi này hay không?”

- `return true;`: processor **claim toàn bộ các annotation types trong tham số `annotations` của lượt gọi**. Các processor **đứng sau** trong cùng vòng sẽ không còn được giao những kiểu đã claim ấy.
- `return false;`: processor **không claim** những kiểu đó; các processor sau vẫn có thể được giao chúng nếu hỗ trợ và còn phù hợp với tập annotation chưa được claim.

`true` không chứng minh processor đã xử lý thành công mọi element và `false` không báo build thất bại. Để báo lỗi biên dịch, dùng `Messager.printMessage(Diagnostic.Kind.ERROR, ...)` hoặc cơ chế báo lỗi đúng nghĩa.

Hai khái niệm phải tách bạch:

1. **Annotation type:** ví dụ `demo.Trace`, được truyền dưới dạng `TypeElement` trong tham số `annotations`.
2. **Element có annotation:** ví dụ một class `@Trace class Task {}`. Muốn tìm các phần tử được chú thích, gọi `roundEnv.getElementsAnnotatedWith(Trace.class)` hoặc biến thể phù hợp.

`process` được gọi qua **nhiều processing rounds**, nên ý nghĩa claim phải hiểu trong bối cảnh **từng round và thứ tự processor**.

## 2. Chữ ký `process` và hai tham số

`Processor` khai báo:

```java
boolean process(
    Set<? extends TypeElement> annotations,
    RoundEnvironment roundEnv
);
```

Khi kế thừa `AbstractProcessor`, thường viết:

```java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    // ...
    return true;
}
```

### Tham số `annotations`

Đây là tập những **annotation interfaces (types)** mà công cụ đang **yêu cầu processor xử lý trong round này**. Nó không phải danh sách mọi annotation xuất hiện trong project và cũng không phải danh sách tất cả class đã được chú thích.

Ví dụ nếu processor hỗ trợ hai kiểu `demo.Trace` và `demo.Validate`, tập `annotations` có thể chứa chỉ một, cả hai hoặc rỗng. Điều này tùy các annotation đang hiện diện, các kiểu đã bị processor trước claim và khả năng công cụ phân phối việc xử lý.

Không nên giả định `annotations.size() == 1` hoặc tập luôn có nội dung. Processor đặc biệt với `@SupportedAnnotationTypes("*")` có thể được gọi khi tập này rỗng.

### Tham số `roundEnv`

`RoundEnvironment` cung cấp thông tin ngữ cảnh vòng xử lý:

- `roundEnv.getRootElements()`: các phần tử gốc của lượt xử lý hiện tại.
- `roundEnv.getElementsAnnotatedWith(Trace.class)`: những element phù hợp mang `@Trace` mà API trả về trong round hiện tại.
- `roundEnv.processingOver()`: `true` khi xử lý annotation đã đến round cuối.
- `roundEnv.errorRaised()`: cho biết lỗi được nêu trong round trước, hữu ích khi xử lý vòng tiếp theo.

`roundEnv.getElementsAnnotatedWith(...)` là thao tác tìm **những phần tử được gắn annotation**; nó khác tập annotation types được công cụ chuyển vào `process`. Khi cần làm việc theo mọi kiểu trong `annotations`, hãy duyệt các `TypeElement` và dùng các API của `RoundEnvironment` hoặc mô hình `javax.lang.model` phù hợp.

## 3. Quy tắc claim: `true` và `false` tác động tới ai?

Giả sử một round có annotation type `demo.Trace`. Hai processor đều khai báo hỗ trợ `demo.Trace`, và được công cụ xét theo thứ tự:

```text
Tập annotation type chưa claim: {demo.Trace}
                 │
                 ▼
        Processor A hỗ trợ Trace?
                 │ có
                 ▼
             A.process(...)
                 │
           ┌─────┴─────┐
         false        true
           │             │
     Trace chưa claim    Trace đã claim
           │             │
           ▼             ▼
 Processor B có thể      Processor B không còn
 được giao Trace         được giao Trace trong round ấy
```

Nếu `Processor A` trả `false`, `Processor B` có thể được gọi với `Trace` khi compiler phân phối tập chưa claim. Nếu `Processor A` trả `true`, `Processor B` không còn `Trace` để nhận trong **round đó**.

| Processor đầu tiên | Giá trị từ `process` | Tình trạng `demo.Trace` trong cùng round | Processor kế tiếp có thể nhận `Trace`? |
|---|---|---|---|
| A quan sát metadata | `false` | Chưa được claim | Có |
| A sở hữu việc xử lý | `true` | Đã được claim | Không, vì type này không còn unmatched |
| A trả `true` với hai types được giao | `true` | Cả hai types được giao đều được claim | Không nhận các types đã claim |
| A trả `false` sau khi báo lỗi bằng `Messager` | `false` | Chưa được claim | Vẫn có thể; báo lỗi và claim là hai trục độc lập |

Lưu ý phạm vi chính xác:

- Claim áp dụng cho **annotation types được công cụ giao**, không phải “đánh dấu từng class đã được kiểm tra”.
- `true` không sửa source, không xóa annotation khỏi class file và không cấm mọi công cụ khác đọc metadata ở thời điểm khác.
- Processor đứng **trước** đã được gọi thì không bị “hủy” kết quả chỉ vì processor sau claim.
- Một processor có thể được gọi tiếp trong **các round sau** nếu nó đã tham gia xử lý; claim ở round hiện tại không tự tắt những lần gọi tiếp theo.
- Nếu processor hỗ trợ nhiều annotation types, `boolean` không cho phép claim chỉ **một phần của tập `annotations` trong cùng một lần gọi**. Trả `true` claim toàn tập đã nhận; muốn phân tách quyền xử lý cần thiết kế tập types/processor phù hợp.

## 4. `@SupportedAnnotationTypes` quyết định processor quan tâm đến kiểu nào

`AbstractProcessor` có thể khai báo những annotation types mình hỗ trợ qua:

```java
import javax.annotation.processing.SupportedAnnotationTypes;

@SupportedAnnotationTypes("demo.Trace")
public class TraceProcessor extends AbstractProcessor {
    // ...
}
```

Đây là đoạn minh họa; còn cần khai báo class, import `AbstractProcessor` và override `process` khi viết chương trình đầy đủ.

Một số mẫu hỗ trợ hợp lệ:

| Khai báo | Ý nghĩa |
|---|---|
| `@SupportedAnnotationTypes("demo.Trace")` | Hỗ trợ kiểu `demo.Trace` |
| `@SupportedAnnotationTypes({"demo.Trace", "demo.Validate"})` | Hỗ trợ hai kiểu |
| `@SupportedAnnotationTypes("demo.*")` | Hỗ trợ các annotation interfaces có tên phù hợp mẫu package/type được Java cho phép |
| `@SupportedAnnotationTypes("*")` | Processor phổ quát: hỗ trợ tất cả annotation interfaces, kể cả tập rỗng |

Tên type phải chính xác; `"Trace"` không thay thế `"demo.Trace"` khi type thuộc package `demo`. API cũng cho phép khai báo hỗ trợ bằng cách override `getSupportedAnnotationTypes()` thay cho annotation cấu hình.

Phân biệt **hỗ trợ** và **claim**:

- `@SupportedAnnotationTypes` quyết định **kiểu annotation processor có thể được giao**.
- `process(...): boolean` quyết định **những kiểu đã được giao có bị claim hay không**.
- Bộ công cụ còn phải **khám phá/khởi tạo processor** từ cấu hình build; chỉ khai báo `@SupportedAnnotationTypes` không tự khiến processor được chạy.

Trong môi trường Java module, cú pháp khai báo supported type còn có dạng kèm prefix tên module khi thích hợp. Với ví dụ classpath Java 17 trong bài này, dùng tên fully qualified như `demo.Trace`.

## 5. Ví dụ Java 17+ hoàn chỉnh: một processor trả `false`, một processor trả `true`

Bộ ví dụ dùng **bốn file** trong package `demo`:

```text
src/
└── demo/
    ├── Trace.java
    ├── Example.java
    ├── ObserveProcessor.java
    └── ClaimProcessor.java
```

Khi biên dịch `Example`, cả hai processor cùng hỗ trợ `demo.Trace`. `ObserveProcessor` chạy trước và **không claim**, `ClaimProcessor` chạy sau và **claim**.

### File 1 — `src/demo/Trace.java`

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface Trace {
    String value();
}
```

`@Trace` phục vụ giai đoạn biên dịch nên chọn `RetentionPolicy.SOURCE`. Annotation processor **không cần `RUNTIME`** để xử lý annotation trên source đang được biên dịch.

### File 2 — `src/demo/Example.java`

```java
package demo;

@Trace("checkout")
public class Example {
}
```

Class `Example` được chú thích bằng `demo.Trace`. Đây là lần sử dụng annotation mà hai processor sẽ được giao trong vòng đầu.

### File 3 — `src/demo/ObserveProcessor.java`

```java
package demo;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("demo.Trace")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class ObserveProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (!roundEnv.processingOver() && !annotations.isEmpty()) {
            System.out.println("ObserveProcessor: "
                    + annotations.iterator().next().getQualifiedName());
        }

        return false; // Không claim Trace.
    }
}
```

`ObserveProcessor` in tên annotation type khi được yêu cầu xử lý `Trace`; trả `false` để processor sau còn có cơ hội tiếp cận `Trace`.

### File 4 — `src/demo/ClaimProcessor.java`

```java
package demo;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("demo.Trace")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class ClaimProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (!roundEnv.processingOver() && !annotations.isEmpty()) {
            System.out.println("ClaimProcessor: "
                    + annotations.iterator().next().getQualifiedName());
        }

        return true; // Claim Trace trong round hiện tại.
    }
}
```

### Cách biên dịch và quan sát kết quả

Từ thư mục chứa `src`, chạy với JDK 17 hoặc mới hơn:

```bash
javac -d out src/demo/Trace.java src/demo/ObserveProcessor.java src/demo/ClaimProcessor.java
javac -cp out -processorpath out -processor demo.ObserveProcessor,demo.ClaimProcessor -d out src/demo/Example.java
```

Lệnh đầu biên dịch annotation type và hai processor. Lệnh thứ hai biên dịch `Example` và chỉ định **tường minh thứ tự processor**: `ObserveProcessor` rồi `ClaimProcessor`.

**Stdout từ hai processor ở lượt có annotation:**

```text
ObserveProcessor: demo.Trace
ClaimProcessor: demo.Trace
```

Tại sao xuất hiện đủ hai dòng?

1. `javac` tìm thấy `@demo.Trace` trên `Example`.
2. Processor `ObserveProcessor` hỗ trợ `demo.Trace` và được gọi trước.
3. `ObserveProcessor` trả `false`; `demo.Trace` vẫn chưa được claim.
4. Processor `ClaimProcessor` cũng hỗ trợ `demo.Trace`, nên được gọi và in dòng thứ hai.
5. `ClaimProcessor` trả `true`, claim `demo.Trace`; không có processor nào đứng sau tiếp tục nhận riêng type ấy trong cùng round.
6. Ở round cuối, `annotations` thường rỗng; điều kiện trong hai processor không in thêm dòng.

Đây là output trực tiếp của `System.out.println` trong processor, không phải output từ một ứng dụng `main`. Trên máy hoặc IDE có thể có thêm thông tin compiler/build ngoài stdout này, tùy cách chạy; hai dòng trên là phần mà processor chủ động in.

### Đổi thứ tự để nhìn thấy tác động của `true`

Chạy với `ClaimProcessor` đứng trước:

```bash
javac -cp out -processorpath out -processor demo.ClaimProcessor,demo.ObserveProcessor -d out src/demo/Example.java
```

**Stdout từ processor cho annotation `Trace`:**

```text
ClaimProcessor: demo.Trace
```

Vì `ClaimProcessor` đã claim `Trace`, `ObserveProcessor` không được giao annotation type `Trace` sau đó trong round ấy. Tuy nhiên, đừng diễn giải rằng `ObserveProcessor` bị xóa khỏi build hoặc vĩnh viễn không thể được gọi: vòng xử lý cuối và các điều kiện khác có thể khiến processor từng tham gia được gọi với tập types rỗng.

### Biến `Example` thành chương trình Java độc lập nếu muốn thử chạy

Annotation processing diễn ra khi **biên dịch**, không đòi hỏi chạy `Example`. Nếu muốn có `main`, bạn có thể thêm:

```java
public static void main(String[] args) {
    System.out.println("Example running");
}
```

vào **bên trong** class `Example`, biên dịch lại rồi chạy:

```bash
java -cp out demo.Example
```

Khi đó stdout ứng dụng chính xác là:

```text
Example running
```

Đoạn `main` ở trên chỉ là phần thêm minh họa, không có trong bản `Example.java` ban đầu của ví dụ biên dịch. Hai processor không tự chạy lại khi thực thi chương trình qua `java`.

## 6. Cùng một annotation type có thể được nhiều processor xem xét

Một annotation type như `demo.Trace` không có “owner” bất biến do Java ghi sẵn. Nhiều processor có thể cùng đăng ký hỗ trợ nó.

Ví dụ pipeline:

```text
@Trace trên Example.java
        │
        ▼
Processor ValidateTrace
        │  đọc metadata, có thể báo lỗi
        │  process(...) -> false
        ▼
Processor GenerateTraceIndex
        │  đọc metadata, có thể sinh file
        │  process(...) -> true
        ▼
Processor khác hỗ trợ Trace
        └─ không còn được giao Trace trong cùng round
```

Trả `false` có ích cho **processor mang tính bổ trợ**, như kiểm tra quy ước, ghi nhận số liệu hoặc quan sát annotation mà không muốn “giành” type với bộ xử lý chính. Trả `true` hợp lý khi processor chủ động nhận xử lý đầy đủ tập annotation types đã được giao và muốn những processor phía sau không cạnh tranh xử lý cùng types trong round ấy.

Nhưng đây không phải quy tắc cứng “validator phải false / generator phải true”. Một processor sinh mã có thể vẫn trả `false` để bộ xử lý khác tiếp tục hoạt động; processor kiểm tra cũng có thể claim một type khi nó thật sự sở hữu type ấy. Điều quan trọng là **ý định phối hợp** và tác động tới các processor khác.

Đừng trông chờ `true` bảo vệ mọi side effect. Các processor khác có thể đã chạy trước đó; các công cụ không tham gia cùng chuỗi processing cũng có thể đọc annotation.

## 7. Vì sao `true` không đồng nghĩa “xử lý thành công”?

Xét processor kiểm tra:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {

    for (TypeElement annotationType : annotations) {
        for (Element element :
                roundEnv.getElementsAnnotatedWith(annotationType)) {
            // Một quy tắc kiểm tra nghiệp vụ.
            if (!isValid(element)) {
                processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Invalid annotation usage",
                    element
                );
            }
        }
    }
    return true;
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập; nó giả định method `isValid` và các import `Element` / `Diagnostic` đã được cung cấp trong một processor thực tế.

Ngay cả khi có lỗi được báo bằng `Diagnostic.Kind.ERROR`, method vẫn có thể trả `true` để claim những annotation types đang được giao. Build thất bại do **diagnostic error**, không do boolean `true`.

Tương tự:

```java
return false;
```

không hề báo compiler rằng công việc của processor đã thất bại. Nó chỉ cho phép các annotation types tiếp tục được xem xét bởi processor phía sau.

Ba cách phản hồi có vai trò khác nhau:

| Cơ chế | Ý nghĩa |
|---|---|
| `return true` / `return false` | Claim hay không claim tập annotation types hiện tại |
| `processingEnv.getMessager().printMessage(ERROR, ...)` | Báo lỗi biên dịch hợp lệ |
| Exception không được bắt từ processor | Tình huống bất thường; có thể khiến annotation processing bị gián đoạn |

Thông thường, hãy dùng `Messager` cho lỗi nguồn mà người dùng có thể sửa, thay vì ném exception không kiểm soát. Phân biệt rõ “lỗi được phát hiện”, “processor có xử lý type” và “compiler có hoàn tất build” là ba trạng thái riêng.

## 8. Phạm vi claim là các types được giao, không phải từng element

Giả sử processor hỗ trợ:

```java
@SupportedAnnotationTypes({
    "demo.Trace",
    "demo.Validate"
})
```

Trong một round, `annotations` có cả hai kiểu. Processor chỉ kiểm tra các element có `@Trace` nhưng trả `true` thì **cả `Trace` và `Validate` có trong tập được giao đều bị claim**.

Không có giá trị trả về như:

```java
return claimOnlyTrace; // Chỉ là boolean, không mang danh sách types.
```

để thể hiện “claim `Trace` nhưng không claim `Validate`” trong cùng lượt gọi.

Nếu cần xử lý một type và giữ type khác cho processor sau, những lựa chọn kiến trúc gồm:

- Tách processor theo nhóm annotation types có quyền claim khác nhau.
- Sử dụng `return false` để không claim tập được giao, đồng thời phối hợp tránh thao tác trùng.
- Chỉ công bố những annotation types thực sự do processor nhận xử lý.
- Thiết kế thứ tự và chính sách xử lý rõ ràng nếu nhiều processor thuộc cùng một bộ công cụ.

Đừng bỏ qua một `TypeElement` trong logic rồi nghĩ rằng nó không bị ảnh hưởng khi processor trả `true`. Phạm vi claim theo **tập `annotations`**, không phụ thuộc số element mà code thực tế đã duyệt.

## 9. Trường hợp đặc biệt: `@SupportedAnnotationTypes("*")`

Dấu `"*"` được `Processor` dùng để biểu diễn **tất cả annotation types**, kể cả tình huống không có annotation type nào đang present trong round.

```java
import javax.annotation.processing.SupportedAnnotationTypes;

@SupportedAnnotationTypes("*")
public class UniversalProcessor extends AbstractProcessor {
    // ...
}
```

Đoạn trên chỉ minh họa cấu hình annotation; cần viết class đầy đủ khi dùng trong thực tế.

### `"*"` đi cùng `return true`

Theo hợp đồng của `Processor`, nếu processor hỗ trợ `"*"` và trả `true`, nó **claim toàn bộ annotation types đang có trong tập được giao**. Điều này có thể khiến các processor khác không còn được giao những types ấy trong round, ngay cả khi universal processor chỉ định làm một bước kiểm tra chung.

Vì vậy, với công cụ quét/kiểm tra mang tính **không độc quyền**:

```java
@SupportedAnnotationTypes("*")
public class ObservationProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        // Quan sát root elements hoặc kiểm tra quy tắc bổ sung.
        return false; // Không chiếm quyền xử lý annotation của processor khác.
    }
}
```

Ví dụ là mảnh minh họa, yêu cầu import các kiểu JSR 269 và khai báo `@SupportedSourceVersion` hoặc override phương thức tương ứng để có cấu hình hoàn chỉnh.

### Tập `annotations` rỗng vẫn có thể được giao cho universal processor

Nếu không có annotation types present trong một round, annotation processing vẫn có thể diễn ra và processor hỗ trợ `"*"` có thể được gọi với **tập rỗng**. Hãy xử lý an toàn:

```java
if (annotations.isEmpty()) {
    // Không có annotation type nào trong tập được giao ở round này.
}
```

Không truy cập `annotations.iterator().next()` mà không kiểm tra. Dù có thể được gọi khi tập rỗng, điều đó không có nghĩa processor sẽ tự động được khám phá và khởi chạy trong mọi cấu hình build: vẫn cần cấu hình công cụ/processor discovery hợp lệ.

Một universal checker nên cân nhắc trả `false`, đặc biệt nếu công cụ chỉ bổ sung kiểm tra và phải đồng tồn tại với các processor xử lý annotation cụ thể.

## 10. Các processing rounds và round cuối

Annotation processing không nhất thiết chỉ có một lượt. Khi processor tạo source file mới, compiler có thể đưa source ấy vào **round sau** để các processor tiếp tục phát hiện annotation.

Ví dụ khái niệm:

```text
Round 1:
  input ban đầu: Example.java có @Trace
  processor đọc Trace, có thể tạo GeneratedExample.java
      │
      ▼
Round 2:
  input: mã nguồn/class sinh ở round trước
  processor tìm annotation trên những phần tử mới
      │
      ▼
Round cuối:
  processingOver() == true
  cơ hội kiểm tra tổng kết, không nên tạo source mới
```

Một processor đã được mời xử lý ở round trước **sẽ tiếp tục được gọi trong các round sau**, bao gồm round cuối, ngay cả khi không có annotation type được giao trong round đó.

Hệ quả:

- Không dùng `annotations.isEmpty()` làm phép kiểm tra duy nhất để quyết định “đây là round cuối”. Dùng `roundEnv.processingOver()`.
- Một lần trả `true` không loại processor khỏi các round sau.
- Nếu processor được gọi với `annotations` rỗng, vẫn phải xử lý hợp lệ, đặc biệt ở round cuối.
- Nếu cần tổng hợp kết quả xuyên round, processor có thể giữ trạng thái giữa các lượt gọi trên **cùng processor instance**; hãy quản lý trùng lặp và trạng thái cẩn thận.
- Thường không tạo source mới khi `processingOver() == true`. Việc tạo file source ở round cuối không tạo một round biên dịch thông thường kế tiếp cho nó và có thể phát sinh cảnh báo.

### `processingOver()` không quyết định giá trị claim

Ví dụ:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    if (roundEnv.processingOver()) {
        // Tổng kết, dọn trạng thái, báo diagnostic nếu cần.
        return false;
    }
    // Xử lý các annotation type đã được giao.
    return true;
}
```

Đoạn là mảnh minh họa. Processor có thể trả các giá trị khác nhau theo round; `Processor` cho phép biến thiên boolean theo tiêu chí riêng. Đừng suy diễn rằng `return false` ở round cuối là lỗi hoặc khiến processor chạy lại vô hạn.

## 11. Một annotation có thể không được giao dù “nó xuất hiện đâu đó”

Một processor chỉ được giao annotation types **theo nguyên tắc present/unmatched của round**, không phải quét toàn bộ classpath hay toàn bộ repository mỗi lần gọi.

Các tình huống đáng chú ý:

### Annotation tồn tại trên dependency đã biên dịch

Nếu một JAR chứa class có annotation nhưng không nằm trong root elements hoặc tập phù hợp của lượt biên dịch hiện tại, processor có thể không được yêu cầu xử lý annotation đó. `@SupportedAnnotationTypes("pkg.Marker")` không tự biến processor thành bộ quét mọi JAR trên classpath.

Nếu dự án cần phân tích dependency, thiết kế một quy trình đọc classpath/mô hình phần tử hoặc công cụ bytecode riêng theo nhu cầu; không kỳ vọng `process` tự cung cấp mọi nơi annotation từng xuất hiện.

### Repeatable annotation được bọc trong container

Khi một repeatable annotation `@Tag` được viết nhiều lần, compiler biểu diễn nó qua container `@Tags`. Theo quy tắc xử lý annotation, những `@Tag` **chỉ xuất hiện bên trong container** không được coi là *present* đơn thuần chỉ vì chúng là phần tử của `@Tags.value()`.

Do đó, processor xử lý annotation lặp nên đăng ký **cả kiểu lặp và kiểu container** trong `getSupportedAnnotationTypes()`, ví dụ:

```java
@SupportedAnnotationTypes({
    "demo.Tag",
    "demo.Tags"
})
```

Điều này tránh bỏ sót những trường hợp compiler phân phối `Tags` là annotation type present thay vì `Tag` trực tiếp. Sau đó processor cần đọc container theo đúng mô hình `javax.lang.model` khi cần lấy dữ liệu con.

### Annotation type đã bị processor trước claim

Nếu một processor đứng trước đã claim `demo.Trace` trong round, processor sau không được giao `Trace` chỉ vì cùng khai báo hỗ trợ nó. Đây là tình huống **phối hợp processors**, không phải annotation biến mất khỏi mã nguồn.

### Processor chưa được khám phá/khởi tạo

Nếu `javac` không được cấu hình để dùng processor, không có lý do gì để `process` được gọi. Hãy kiểm tra `-processor`, processor path/module path, cấu hình công cụ build và cơ chế đăng ký dịch vụ (`META-INF/services/javax.annotation.processing.Processor`) khi sử dụng discovery tự động.

## 12. Thiết kế processor có trách nhiệm

Một processor có thể vừa nhận diện annotation type vừa đọc các element và phát diagnostic, nhưng nên tránh claim quá rộng. Mẫu tư duy:

```text
Bước 1: Xác định annotation types mình thực sự hỗ trợ.
Bước 2: Xem annotations được giao trong round hiện tại.
Bước 3: Lấy elements phù hợp bằng RoundEnvironment.
Bước 4: Thực thi logic kiểm tra/sinh mã.
Bước 5: Chọn boolean claim dựa trên chính sách phối hợp.
Bước 6: Chấp nhận được gọi ở các round tiếp theo, kể cả round cuối.
```

Đề xuất theo mục tiêu:

| Mục tiêu | Gợi ý boolean | Giải thích |
|---|---|---|
| Processor sở hữu hoàn toàn một annotation type cụ thể và muốn ngăn processor sau cùng xử lý type ấy | `true` | Claim toàn tập được giao |
| Checker độc lập chỉ quan sát/đưa cảnh báo, mong các processor khác tiếp tục xử lý | `false` | Không claim |
| Universal checker `"*"` chạy cạnh nhiều annotation processors | Thường `false` | Tránh claim mọi annotation type |
| Processor có nhiều annotation types nhưng chỉ muốn claim một phần | Xem lại kiến trúc | Một boolean không diễn đạt claim một phần trong cùng call |
| Processor bị lỗi ở một element nhưng vẫn xác định chính sách claim | `true` hoặc `false` tùy quyền xử lý | Báo lỗi bằng `Messager`, không dùng boolean để biểu thị lỗi |
| Round cuối không còn annotation mới | Không có đáp án bắt buộc | Dùng `processingOver()`, bảo đảm hàm chịu được tập rỗng |

Ngoài ra:

- Không phụ thuộc vào thứ tự duyệt một `Set<? extends TypeElement>` để quyết định annotation nào ưu tiên nếu không chủ động sắp xếp.
- Đừng chạy những side effect không idempotent mỗi khi `process` được gọi; processor có thể tham gia nhiều round.
- Khi dùng `Filer` tạo source/resource, tránh cố tạo lại cùng một file nhiều lần (có thể dẫn tới `FilerException`).
- Ghi diagnostic có vị trí element cụ thể để người học/sử dụng nhận thông tin dễ hiểu.
- Thử nghiệm với **hai processor** hỗ trợ cùng một annotation type để phát hiện sớm việc claim không mong muốn.
- Nếu trả `true`, bảo đảm bạn thật sự chấp nhận trách nhiệm với mọi annotation types đang được giao, không chỉ một type được chọn tùy tiện.

## 13. Các lỗi thường gặp và cách sửa

### 13.1. Nghĩ `return true` nghĩa là “build thành công”

Sai. Nó có nghĩa claim annotation types. Build vẫn có thể thất bại vì lỗi cú pháp, lỗi compiler hoặc `Diagnostic.Kind.ERROR` do processor báo.

### 13.2. Nghĩ `return false` nghĩa là “xử lý thất bại”

Sai. Một validator có thể đã hoàn tất nhiệm vụ và chủ động trả `false` để processor khác tiếp tục nhận type.

### 13.3. Bỏ qua giá trị boolean vì “chỉ có một processor”

Ngay cả khi hiện tại chỉ có một processor, cấu hình build tương lai có thể thêm processor khác. Giá trị trả về là một phần của chính sách phối hợp, không nên chọn ngẫu nhiên.

### 13.4. Dùng `"*"` và `return true` cho công cụ chỉ giám sát

Điều này có thể claim nhiều annotation types ngoài ý định, chặn processor chuyên dụng đứng sau. Hãy cân nhắc `return false` cho checker phổ quát.

### 13.5. Tưởng claim là độc quyền vĩnh viễn

Claim chỉ điều phối các annotation types **chưa được claim trong round hiện tại**. Nó không ngăn processor trước đó, không xóa metadata, không tắt các round sau và không bảo đảm toàn bộ hệ thống chỉ có một consumer.

### 13.6. Nhầm tập `annotations` với danh sách các class được chú thích

Tham số `annotations` chứa những `TypeElement` biểu diễn **annotation types**; để tìm class/method/field đã gắn annotation, dùng `roundEnv.getElementsAnnotatedWith(...)` và lọc theo `ElementKind` hoặc kiểm tra mô hình phần tử khi cần.

### 13.7. Giả định `annotations` luôn khác rỗng

Processor đã được gọi trong các round tiếp theo, kể cả round cuối, có thể nhận tập rỗng. Processor `"*"` cũng có thể được gọi trong tình huống không có types present. Hãy kiểm tra `isEmpty()` và `processingOver()` đúng mục đích.

### 13.8. Chỉ khai báo `@SupportedAnnotationTypes` rồi chờ processor chạy

Processor phải được khám phá và nạp. Với `javac`, kiểm tra `-processor` và `-processorpath` hoặc cơ chế module path/đăng ký dịch vụ phù hợp. Lệnh ví dụ đã dùng `-processor` tường minh để loại bỏ sự phụ thuộc vào service discovery.

### 13.9. Bỏ sót container của annotation lặp

Nếu `@Tag` có thể xuất hiện nhiều lần và tạo `@Tags`, đăng ký hỗ trợ cả `Tag` lẫn `Tags` rồi xử lý trường hợp container đúng ngữ nghĩa. Không cho rằng inner annotation luôn hiện diện như type độc lập trong tập `annotations`.

### 13.10. Cho rằng báo `ERROR` tự động claim annotation

Một diagnostic lỗi không tự quyết định boolean của `process`. Nếu processor muốn claim tập annotations, vẫn phải trả `true`; nếu muốn giữ types cho processor khác, trả `false`. Hai quyết định độc lập.

## 14. Bài tập hiểu rõ quy tắc

Giả sử trong một round có tập unmatched ban đầu:

```text
{ demo.Trace, demo.Validate }
```

Có ba processor theo thứ tự:

```text
P1 supports demo.Trace
P2 supports demo.Trace và demo.Validate
P3 supports demo.Validate
```

Hãy phân tích các tình huống:

1. P1 nhận `Trace` và trả `true`. P2 còn có thể nhận `Trace` không?
2. Cùng tình huống, P2 có thể được giao `Validate` không?
3. P1 trả `false`. P2 có thể nhận cả `Trace` và `Validate` không?
4. P2 được giao hai types và trả `true`, P3 có thể nhận `Validate` trong round ấy không?
5. P2 chỉ đọc elements `@Trace` nhưng được giao cả hai types rồi trả `true`, `Validate` có bị claim không?
6. Nếu P2 báo `Diagnostic.Kind.ERROR` nhưng trả `false`, boolean này báo xử lý thất bại không?
7. Một universal processor `"*"` đứng đầu trả `true`, chuyện gì xảy ra với các types trong unmatched set?
8. Một processor đã được gọi ở round đầu và claim `Trace`; khi chuyển sang round cuối không có annotation mới, nó có còn có thể được gọi không?
9. Khi `annotations` rỗng, có nên gọi ngay `annotations.iterator().next()` không?
10. Khi `@Tag` lặp được chứa trong `@Tags`, chỉ đăng ký hỗ trợ `Tag` có bảo đảm đủ mọi lần sử dụng không?

**Đáp án:**

1. **Không.** `Trace` đã bị P1 claim trong round.
2. **Có thể.** `Validate` chưa bị P1 claim; P2 có khai báo hỗ trợ type này.
3. **Có thể.** Cả hai types vẫn chưa claim, tùy tập mà compiler giao P2 trong round.
4. **Không.** Nếu P2 nhận cả hai và trả `true`, `Validate` đã bị claim.
5. **Có.** Boolean claim cả tập được giao, không chỉ type mà code đã đọc.
6. **Không.** `false` nghĩa là không claim; lỗi biên dịch do `Diagnostic.Kind.ERROR`.
7. **Mọi types được giao đều bị claim**, khiến các processor sau không còn nhận chúng trong round.
8. **Có.** Các processor từng được mời trong một round tiếp tục được mời ở các round sau, kể cả round cuối.
9. **Không.** Phải kiểm tra tập rỗng và xử lý `processingOver()` khi thích hợp.
10. **Không bảo đảm.** Nên hỗ trợ cả repeatable type và container type theo khuyến nghị API.

## 15. Checklist cuối bài

- `process` trả `true` để **claim tập annotation types đang được giao**, không phải để báo thành công.
- `process` trả `false` để **không claim**, không phải để báo thất bại.
- Claim tác động đến processor **đứng sau trong cùng round**, không thu hồi kết quả processor trước.
- `annotations` chứa annotation **types** dạng `TypeElement`, không phải các class/method được gắn annotation.
- Dùng `roundEnv.getElementsAnnotatedWith(...)` để lấy elements tương ứng.
- Khai báo supported types chính xác bằng `@SupportedAnnotationTypes` hoặc `getSupportedAnnotationTypes()`.
- Processor cần được build/discover/cấu hình để compiler thực sự gọi `process`.
- Nếu dùng `"*"` làm checker phổ quát, thường trả `false` để không chặn processors khác.
- Giá trị boolean không cho phép claim có chọn lọc một phần của tập `annotations` được giao trong cùng call.
- Một processor có thể được gọi qua nhiều round; dùng `roundEnv.processingOver()` thay vì đoán dựa vào `annotations.isEmpty()`.
- Luôn xử lý tập `annotations` rỗng và tránh tạo lại tệp trong nhiều round.
- Báo lỗi thực sự bằng `Messager` và `Diagnostic.Kind.ERROR`, độc lập với boolean trả về.
- Khi làm việc với repeatable annotation, cân nhắc đăng ký hỗ trợ cả kiểu lặp và container.
- Viết thử một build có nhiều processor cùng hỗ trợ type để xác minh thứ tự và chính sách claim.

**Nguồn đối chiếu:** Java SE 17, `javax.annotation.processing.Processor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html ; `RoundEnvironment`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html .

Điểm mấu chốt: **`process` là cơ chế phối hợp giữa các processor trong từng processing round**. Hiểu rõ boolean claim, tập `TypeElement` được giao và thứ tự processors giúp tránh việc vô tình “nuốt” annotation khiến processor khác không còn nhận được công việc.