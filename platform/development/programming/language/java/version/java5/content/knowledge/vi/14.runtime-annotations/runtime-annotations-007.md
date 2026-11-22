# Các lỗi khi kiểu annotation hoặc giá trị tham chiếu không còn phù hợp

## Vấn đề: mã nguồn từng hợp lệ nhưng dữ liệu lúc chạy đã lệch phiên bản

Annotation được biên dịch cùng lớp sử dụng nó, nhưng kiểu annotation và các kiểu được tham chiếu có thể được cung cấp bởi những thư viện khác. Nếu các thành phần đó không còn tương thích khi chạy, reflection có thể gặp dữ liệu annotation không đọc được.

Ví dụ:

- Một thuộc tính kiểu `Class<?>` trỏ đến lớp không có trong môi trường chạy.
- Một thuộc tính enum chứa tên hằng đã bị loại khỏi phiên bản enum đang dùng.
- Một thuộc tính annotation đổi từ `int` sang `String`, trong khi lớp được gắn annotation chưa được biên dịch lại.
- Kiểu annotation thêm thuộc tính bắt buộc, nhưng dữ liệu đã biên dịch trước đó không có giá trị cho thuộc tính mới.

Đây vẫn là vấn đề của Java hiện đại, nhất là khi nâng cấp thư viện, triển khai nhiều thành phần độc lập hoặc đóng gói thiếu phụ thuộc. Bài dùng reflection trên JDK 17 trở lên; không cần API đã ngừng khuyến nghị.

Cần phân biệt **tìm thấy annotation** với **đọc thành công mọi thuộc tính của annotation**. Hai việc này không tương đương.

## Mô hình để chẩn đoán

Có ba nguồn cần khớp nhau:

1. **Lớp được gắn annotation:** chứa dữ liệu đã ghi tại lúc biên dịch.
2. **Kiểu annotation đang được nạp:** định nghĩa các thuộc tính, kiểu trả về và giá trị mặc định hiện tại.
3. **Các kiểu được giá trị annotation tham chiếu:** chẳng hạn lớp trong `Class<?>` hoặc kiểu enum và các hằng của nó.

Nếu chỉ kiểm tra mã nguồn mới nhất mà không kiểm tra các tệp class thực sự đang chạy, có thể bỏ sót sự lệch giữa ba nguồn này.

Một số lỗi được biểu hiện khi gọi thuộc tính annotation. Vì vậy đoạn mã có thể lấy được một annotation khác `null`, rồi mới lỗi tại lệnh như `schema.type()` hoặc `schema.owner()`.

Quy tắc reflection liên quan được tổng hợp tại [AnnotatedElement](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).

## Bản đồ các lỗi thường gặp

| Lỗi | Tình huống điển hình | Điểm cần kiểm tra |
| --- | --- | --- |
| `TypeNotPresentException` | Đọc thuộc tính `Class` nhưng kiểu được tham chiếu không có sẵn | Tên kiểu, phụ thuộc và ngữ cảnh nạp lớp |
| `EnumConstantNotPresentException` | Đọc thuộc tính enum nhưng hằng được ghi trong annotation không còn tồn tại | Phiên bản enum và tên hằng |
| `AnnotationTypeMismatchException` | Giá trị được lưu không phù hợp với kiểu trả về hiện tại của thuộc tính | Kiểu thuộc tính trước/sau nâng cấp |
| `IncompleteAnnotationException` | Thiếu giá trị của một thuộc tính bắt buộc không có mặc định | Thuộc tính mới và dữ liệu annotation đã biên dịch |
| `AnnotationFormatError` | Dữ liệu hoặc cấu trúc annotation không hợp lệ | Đầu ra class, công cụ biến đổi bytecode và cấu trúc annotation lặp |

Bốn lỗi đầu là các ngoại lệ không được kiểm tra bắt buộc khi biên dịch, thuộc nhánh `RuntimeException`. `AnnotationFormatError` thuộc nhánh `Error`, không phải `Exception`.

Không dùng một nhãn chung “reflection bị lỗi” cho tất cả các trường hợp. Mỗi loại cho biết một quan hệ khác nhau đang bị phá vỡ.

## 1. TypeNotPresentException: giá trị Class trỏ đến kiểu không có sẵn

Giả sử annotation có thuộc tính:

```java
Class<?> type();
```

Một lớp được biên dịch với `@Schema(type = OptionalFeature.class, ...)`. Đến lúc chạy, lớp `OptionalFeature` không có trong đường nạp lớp phù hợp. Lệnh đọc `schema.type()` có thể phát sinh `TypeNotPresentException`.

Thông tin hữu ích:

- `exception.typeName()`: tên đầy đủ của kiểu không có sẵn.
- `exception.getCause()`: nguyên nhân bên dưới nếu có.

Không đồng nhất lỗi này với `ClassNotFoundException`. `ClassNotFoundException` là ngoại lệ được kiểm tra, thường gặp ở thao tác nạp lớp trực tiếp như `Class.forName`; `TypeNotPresentException` là ngoại lệ không được kiểm tra và có thể xuất hiện qua API đọc annotation.

Cũng cần phân biệt **thiếu lớp được một thuộc tính Class tham chiếu** với **thiếu chính kiểu annotation**. Đó là các tình huống khác nhau; không suy luận rằng mọi kiểu bị thiếu đều nhất thiết xuất hiện dưới cùng một ngoại lệ tại cùng một API.

Xem [TypeNotPresentException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/TypeNotPresentException.html).

## 2. EnumConstantNotPresentException: tên hằng enum không còn hợp lệ

Giá trị enum trong annotation được gắn với kiểu enum và tên hằng. Nếu dữ liệu đã biên dịch chứa `State.REMOVED` nhưng enum đang chạy chỉ còn `ACTIVE`, đọc thuộc tính đó không thể tự chọn một hằng khác.

Các thông tin chẩn đoán:

- `exception.enumType()`: kiểu enum liên quan.
- `exception.constantName()`: tên hằng không tìm được.

Không “sửa” bằng cách tự thay hằng bị thiếu bằng phần tử đầu tiên của enum. Giá trị thay thế có thể mang ý nghĩa hoàn toàn khác.

Cách xử lý là đồng bộ phiên bản, giữ tương thích với hằng còn được dữ liệu đã triển khai sử dụng, hoặc di chuyển dữ liệu và biên dịch lại các lớp chịu ảnh hưởng theo thiết kế đã xác định.

Xem [EnumConstantNotPresentException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/EnumConstantNotPresentException.html).

## 3. AnnotationTypeMismatchException: kiểu giá trị đã lệch với định nghĩa

Giả sử phiên bản trước khai báo `int size();`, và một lớp được gắn `@Schema(size = 3, ...)`. Sau đó phiên bản annotation đang chạy đổi thành `String size();`.

Dữ liệu đã lưu vẫn là số nguyên, còn phương thức thuộc tính hiện tại yêu cầu chuỗi. Khi đọc thuộc tính, có thể nhận `AnnotationTypeMismatchException`.

Các thông tin hữu ích:

- `exception.element()`: phương thức thuộc tính bị lệch kiểu.
- `exception.foundType()`: mô tả kiểu dữ liệu tìm thấy; không nên coi định dạng chuỗi này là giao thức ổn định để phân tích máy móc.

Java không tự chuyển số 3 thành chuỗi `"3"` trong quá trình đọc annotation. Nếu muốn đổi hợp đồng kiểu thuộc tính, cần xem đó là thay đổi hợp đồng thư viện và có kế hoạch di chuyển, không chỉ thay kiểu trong một tệp nguồn.

Xem [AnnotationTypeMismatchException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/AnnotationTypeMismatchException.html).

## 4. IncompleteAnnotationException: thiếu thuộc tính không có mặc định

Một kiểu annotation có thể thêm `String owner();` mà không có `default`. Các lần sử dụng được biên dịch trước đó không chứa giá trị `owner`. Khi đọc `schema.owner()`, có thể nhận `IncompleteAnnotationException`.

Thông tin hữu ích:

- `exception.annotationType()`: kiểu annotation liên quan.
- `exception.elementName()`: tên thuộc tính thiếu giá trị.

Điểm khác với lỗi lệch kiểu:

- `AnnotationTypeMismatchException`: có dữ liệu nhưng kiểu không phù hợp.
- `IncompleteAnnotationException`: không có giá trị phù hợp và cũng không có mặc định để dùng.

Thêm một thuộc tính với giá trị mặc định có thể giúp dữ liệu annotation đã biên dịch trước đó vẫn đọc được thuộc tính mới. Tuy nhiên, phải chọn mặc định có ý nghĩa đúng; không dùng chuỗi rỗng chỉ để giấu việc thiếu một thông tin bắt buộc.

Xem [IncompleteAnnotationException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/IncompleteAnnotationException.html).

## 5. AnnotationFormatError: cấu trúc metadata không hợp lệ

`AnnotationFormatError` biểu thị vấn đề ở định dạng hoặc cấu trúc annotation mà API đang đọc.

Một trường hợp được API nêu rõ là annotation lặp: kiểu annotation dùng `@Repeatable(Container.class)`, nhưng kiểu chứa không có phương thức `value()` với kiểu trả về đúng là mảng của kiểu annotation được chứa.

Trình biên dịch thường ngăn các khai báo không hợp lệ khi biên dịch đồng bộ từ nguồn. Nhưng các phiên bản class bị trộn hoặc công cụ biến đổi bytecode có thể tạo ra đầu vào không còn đáp ứng hợp đồng.

Lỗi này không được bắt bởi `catch (Exception ex)`. Không vì thế mà thêm `catch (Throwable ex)` để mọi lỗi đều bị bỏ qua. Hãy chẩn đoán đầu ra build hoặc giới hạn xử lý ở một ranh giới rõ ràng nếu hệ thống có cơ chế cô lập thành phần lỗi.

Ví dụ trong bài tái hiện bốn ngoại lệ phía trên bằng các nguồn Java hợp lệ ở từng phiên bản. Nó không chỉnh bytecode để cố tạo `AnnotationFormatError`.

Xem [AnnotationFormatError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/AnnotationFormatError.html).

## Thí nghiệm đầy đủ: dữ liệu V1 được đọc bằng định nghĩa V2

Thí nghiệm chủ động tạo sự lệch phiên bản để quan sát lỗi. Đây không phải cách đóng gói ứng dụng bình thường.

Dùng một thư mục thử nghiệm mới, chưa chứa các đầu ra `build-v1` hoặc `runtime` từ lần thử trước. Tạo các tệp theo cây sau:

```text
project/
├── v1/
│   └── compat/
│       ├── Schema.java
│       ├── State.java
│       ├── OptionalFeature.java
│       └── Model.java
├── v2/
│   └── compat/
│       ├── Schema.java
│       └── State.java
└── app/
    └── compat/
        └── Main.java
```

Không biên dịch các nguồn V1 và V2 trong cùng một lệnh: chúng cố ý khai báo các phiên bản khác nhau của cùng tên kiểu.

### Nguồn V1: hợp lệ tại thời điểm biên dịch

Tệp `v1/compat/Schema.java`:

```java
package compat;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Schema {
    Class<?> type();
    State state();
    int size();
}
```

Tệp `v1/compat/State.java`:

```java
package compat;

public enum State {
    ACTIVE, REMOVED
}
```

Tệp `v1/compat/OptionalFeature.java`:

```java
package compat;

public class OptionalFeature {
}
```

Tệp `v1/compat/Model.java`:

```java
package compat;

@Schema(type = OptionalFeature.class, state = State.REMOVED, size = 3)
public class Model {
}
```

Lúc biên dịch V1, lớp được tham chiếu tồn tại, hằng enum tồn tại, `size` là `int` và chưa có yêu cầu `owner`. Không có lỗi nguồn ở tổ hợp này.

### Nguồn V2: định nghĩa đã thay đổi

Tệp `v2/compat/Schema.java`:

```java
package compat;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Schema {
    Class<?> type();
    State state();
    String size();
    String owner();
}
```

Tệp `v2/compat/State.java`:

```java
package compat;

public enum State {
    ACTIVE
}
```

Ở V2:

- `size` đổi sang `String`.
- `owner` được thêm và không có mặc định.
- `State` không còn hằng `REMOVED`.
- Ta sẽ không đưa `OptionalFeature.class` vào đầu ra lúc chạy.

### Chương trình đọc và tách riêng từng lỗi

Tệp `app/compat/Main.java`:

```java
package compat;

import java.lang.annotation.AnnotationTypeMismatchException;
import java.lang.annotation.IncompleteAnnotationException;
import java.util.function.Supplier;

public class Main {
    static void read(String name, Supplier<?> action) {
        try {
            System.out.println(name + "=" + action.get());
        } catch (TypeNotPresentException
                | EnumConstantNotPresentException
                | AnnotationTypeMismatchException
                | IncompleteAnnotationException ex) {
            System.out.println(name + "=" + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        Class<?> model = Class.forName("compat.Model");
        Schema schema = model.getAnnotation(Schema.class);
        System.out.println("annotationObtained=" + (schema != null));
        if (schema == null) {
            throw new IllegalStateException("Schema is missing");
        }

        read("type", schema::type);
        read("state", schema::state);
        read("size", schema::size);
        read("owner", schema::owner);
    }
}
```

Hàm `read` cố ý bắt riêng bốn ngoại lệ đang được khảo sát để có thể in kết quả của cả bốn thuộc tính trong cùng một lần chạy. Đây là bộ quan sát cho thí nghiệm, không phải mẫu xử lý lỗi nghiệp vụ bằng cách bỏ qua cấu hình hỏng.

`Main` dùng `Class.forName("compat.Model")` để không cần biên dịch lại `Model` theo định nghĩa V2. Các lời gọi `schema.type()`, `state()`, `size()` và `owner()` được thực hiện riêng biệt thông qua `Supplier`.

### Biên dịch và sắp xếp đầu ra

Các lệnh dưới đây dùng PowerShell; chạy từ thư mục `project`. Hai lệnh `javac` mỗi lệnh được viết trên một dòng:

```powershell
javac -encoding UTF-8 -d build-v1 v1/compat/Schema.java v1/compat/State.java v1/compat/OptionalFeature.java v1/compat/Model.java
javac -encoding UTF-8 -d runtime v2/compat/Schema.java v2/compat/State.java app/compat/Main.java
Copy-Item -LiteralPath build-v1/compat/Model.class -Destination runtime/compat/Model.class
java -cp runtime compat.Main
```

Chỉ sao chép **Model.class** từ V1 sang đầu ra V2. Không sao chép `Schema.class`, `State.class` hoặc `OptionalFeature.class` của V1.

Classpath khi chạy chỉ là `runtime`, không bao gồm `build-v1`. Nếu thêm toàn bộ `build-v1` vào classpath, lớp `OptionalFeature` có thể lại được tìm thấy, làm mất điều kiện tái hiện lỗi thiếu kiểu.

Đầu ra lúc chạy có dạng:

```text
runtime/
└── compat/
    ├── Main.class
    ├── Model.class       (du lieu annotation tu V1)
    ├── Schema.class      (dinh nghia V2)
    └── State.class       (dinh nghia V2)
```

### Kết quả

```text
annotationObtained=true
type=TypeNotPresentException
state=EnumConstantNotPresentException
size=AnnotationTypeMismatchException
owner=IncompleteAnnotationException
```

Kết quả đã phân tách rõ:

1. Việc lấy `Schema` vẫn thành công.
2. Thuộc tính `type` không đọc được vì không có `compat.OptionalFeature`.
3. Thuộc tính `state` không đọc được vì `REMOVED` không có trong enum V2.
4. Thuộc tính `size` gặp dữ liệu số nguyên trong khi định nghĩa V2 yêu cầu chuỗi.
5. Thuộc tính `owner` không có giá trị trong dữ liệu V1 và V2 không cung cấp mặc định.

Nếu biên dịch lại `Model.java` theo V2, nhiều vấn đề sẽ bị trình biên dịch phát hiện ngay. Thí nghiệm cố ý giữ dữ liệu V1 để cho thấy sự khác biệt giữa kiểm tra mã nguồn đồng bộ và đọc dữ liệu class đã triển khai.

## Thay đổi giá trị mặc định có thể đổi hành vi mà không ném lỗi

Không phải mọi sự lệch kỳ vọng đều có ngoại lệ.

Ví dụ, một thuộc tính `String mode() default "safe";` được dùng mà không ghi giá trị trực tiếp. Nếu phiên bản annotation mới đổi mặc định thành `"fast"`, các lần sử dụng đã biên dịch có thể được đọc với mặc định mới mà không cần thay dữ liệu ở lớp được gắn annotation.

Giá trị mặc định không được sao chép vào mọi lần sử dụng annotation lúc biên dịch; nó được áp dụng khi đọc theo định nghĩa hiện hành. Vì vậy:

- Biên dịch thành công không chứng minh ý nghĩa cấu hình được giữ nguyên.
- Không xuất hiện ngoại lệ cũng không chứng minh hành vi vẫn giống trước.
- Những mặc định có ý nghĩa nghiệp vụ cần được xem xét và kiểm thử khi nâng cấp.

Đặc tả về tiến hóa kiểu annotation nằm tại [JLS §13.5.8](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.5.8).

## Cách chẩn đoán có hệ thống

### Xác định thao tác thực sự thất bại

Phân biệt lỗi khi:

- Nạp lớp cần khảo sát.
- Tìm annotation.
- Đọc một thuộc tính cụ thể.
- Xử lý giá trị đã đọc.

Không chỉ ghi “không đọc được annotation”. Cần biết thuộc tính nào và kiểu lỗi nào đã xuất hiện. Có thể lấy thông tin chuyên biệt từ từng ngoại lệ như tên kiểu, tên hằng enum hoặc tên thuộc tính.

Nếu công cụ gọi thuộc tính bằng `Method.invoke`, lỗi ở bên trong có thể được bọc bởi `InvocationTargetException`. Khi đó cần xem nguyên nhân được bọc; đừng nhầm lớp vỏ phản chiếu với lỗi annotation gốc.

### Đối chiếu đầu ra đang chạy

Kiểm tra:

1. Phiên bản thư viện cung cấp kiểu annotation.
2. Phiên bản lớp được gắn annotation.
3. Phụ thuộc chứa các lớp và enum được tham chiếu.
4. Các bản class trùng tên trong classpath hoặc các bộ nạp lớp khác nhau.
5. Bước đóng gói, tối ưu hoặc biến đổi bytecode có giữ metadata đúng hay không.

Trong môi trường triển khai, mã nguồn trên máy phát triển có thể không phải bản class đang được JVM nạp. Cần truy về nguồn của đầu ra thực tế thay vì chỉ chỉnh nguồn rồi chạy lại một bản đóng gói chưa thay đổi.

### Sửa hợp đồng và triển khai đồng bộ

Tùy nguyên nhân:

- Bổ sung đúng phụ thuộc nếu giá trị Class tham chiếu đến một kiểu cần tồn tại.
- Khôi phục khả năng tương thích hoặc di chuyển các lần sử dụng trước khi bỏ hằng enum.
- Tránh đổi kiểu thuộc tính annotation tại chỗ khi vẫn còn các lớp đã biên dịch theo hợp đồng trước.
- Thêm mặc định chỉ khi giá trị đó thật sự hợp lệ cho các lần sử dụng hiện hữu.
- Biên dịch lại, kiểm tra và triển khai các thành phần liên quan cùng nhau khi thay đổi hợp đồng yêu cầu điều đó.

Một lần build sạch có thể giúp loại bỏ đầu ra trộn phiên bản, nhưng không tự giải quyết một hợp đồng thay đổi sai hoặc một phụ thuộc vẫn bị thiếu ở môi trường chạy.

## Nguyên tắc xử lý lỗi trong công cụ đọc annotation

Nếu annotation cung cấp cấu hình bắt buộc, dữ liệu không đọc được cần trở thành lỗi chẩn đoán rõ ràng trước khi hệ thống sử dụng cấu hình đó. Không âm thầm thay bằng giá trị tùy ý rồi tiếp tục như thể cấu hình hợp lệ.

Nếu annotation thuộc một tính năng tùy chọn, có thể cô lập hoặc bỏ qua tính năng theo quy tắc đã được thiết kế, nhưng phải giữ lại nguyên nhân và cho biết phần nào không được kích hoạt.

Nên kiểm tra các thuộc tính cần dùng ở ranh giới nạp cấu hình, thay vì chỉ kiểm tra annotation khác `null`. Đừng coi việc in đối tượng annotation ra log là bằng chứng đã xác minh hết mọi thuộc tính.

Bắt ngoại lệ chỉ có giá trị khi có hành động tiếp theo rõ ràng: báo lỗi cấu hình, dừng khởi tạo thành phần hoặc cô lập chức năng theo hợp đồng. Thêm `catch` rộng để che lỗi không làm dữ liệu annotation trở lại tương thích.

## Thực hành kiểm chứng

Mỗi lần thử nên dùng một thư mục đầu ra mới để không lẫn các class của lần trước:

1. Chạy thí nghiệm ban đầu và đối chiếu đủ năm dòng.
2. Đưa thêm riêng `OptionalFeature.class` của V1 vào thư mục `runtime/compat`; lỗi ở thuộc tính `type` biến mất, các lỗi còn lại vẫn giữ nguyên.
3. Thêm lại `REMOVED` vào enum V2 rồi biên dịch V2; kiểm tra riêng lỗi enum.
4. Đổi `size()` ở V2 về `int`; thuộc tính này sẽ đọc được giá trị 3 của dữ liệu V1.
5. Thêm `default "unknown"` cho `owner()`; xác nhận đọc được giá trị mặc định, rồi đánh giá liệu mặc định đó có thực sự phù hợp với thiết kế.
6. Giải thích vì sao một annotation khác `null` không đủ làm bằng chứng cho cấu hình hợp lệ.

Mục tiêu là liên hệ được từng lỗi với **dữ liệu annotation đã biên dịch, định nghĩa đang nạp và kiểu được giá trị tham chiếu**, thay vì xử lý tất cả bằng một nhánh lỗi chung.
