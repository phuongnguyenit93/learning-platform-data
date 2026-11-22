# Phân biệt ràng buộc container với ràng buộc phần tử trong Jakarta Bean Validation và Spring

## 1. Vấn đề cốt lõi: danh sách tồn tại không có nghĩa các phần tử hợp lệ

Trong API Spring, giả sử khách hàng gửi danh sách mã sản phẩm khi tạo đơn hàng. Có ba quy tắc khác nhau:

1. **Danh sách phải tồn tại**: không được bằng `null`.
2. **Danh sách phải có phần tử**: không được là danh sách rỗng.
3. **Từng mã trong danh sách phải hợp lệ**: không được `null`, rỗng hoặc chỉ chứa khoảng trắng.

Ba quy tắc này **không thể thay thế nhau**:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

class OrderRequest {
    @NotEmpty
    private List<@NotBlank String> productCodes;
}
```

Trong ví dụ trên:

- `@NotEmpty` đặt **trước kiểu `List`** kiểm tra **bản thân container** `productCodes` (không null và không rỗng).
- `@NotBlank` đặt **trên type argument `String`** kiểm tra **từng phần tử** được trích xuất từ danh sách.
- Một danh sách có phần tử `"   "` không vượt qua `@NotBlank`, dù bản thân danh sách có kích thước lớn hơn 0.
- Việc kiểm tra phần tử chỉ diễn ra khi có một container để duyệt; ràng buộc phần tử không thay thế ràng buộc bắt buộc có container.

Nội dung này thuộc **Jakarta Bean Validation**, với các API `jakarta.validation.*` trong Spring Framework 6 / Spring Boot 3. Hệ sinh thái Spring cũ có thể dùng namespace `javax.validation.*`. Cần lựa chọn provider và namespace cùng thế hệ.

### 1.1. Bảng phân biệt nhanh

| Khai báo | Kiểm tra gì? | `null` container | Container rỗng | Phần tử `null` |
| --- | --- | --- | --- | --- |
| `@NotNull List<String> xs` | Danh sách phải khác `null` | Vi phạm | Đạt | Đạt |
| `@NotEmpty List<String> xs` | Danh sách khác `null` và có ít nhất một phần tử | Vi phạm | Vi phạm | Đạt |
| `List<@NotNull String> xs` | Từng phần tử khác `null` | Không bị từ chối bởi constraint này | Đạt | Vi phạm nếu có phần tử null |
| `List<@NotBlank String> xs` | Từng chuỗi có nội dung không phải whitespace | Không bị từ chối bởi constraint này | Đạt | Vi phạm nếu có phần tử null |
| `@NotEmpty List<@NotBlank String> xs` | Danh sách có phần tử **và** từng chuỗi không blank | Vi phạm | Vi phạm | Vi phạm nếu có phần tử null |

**`@NotNull` và `@NotEmpty` đặt trên danh sách không mặc nhiên kiểm tra nội dung các phần tử.** Ngược lại, chỉ đặt `@NotBlank` trong dấu `<...>` không đảm bảo người dùng phải cung cấp một danh sách. Các annotation này hoạt động trên **vị trí** mà chúng được khai báo.

## 2. Ràng buộc container: kiểm tra chính List, Set, Map, array hoặc Optional

**Container-level constraint** là constraint áp dụng cho đối tượng chứa dữ liệu. Ví dụ:

```java
@NotNull
private List<String> tags;

@NotEmpty
private List<String> productCodes;

@Size(min = 1, max = 5)
private Set<String> categories;

@NotEmpty
private Map<String, Integer> quantities;
```

Đây là các field minh họa, chưa tạo thành class Java có thể chạy độc lập.

### 2.1. Ý nghĩa của các constraint thường gặp

- `@NotNull`: container **không phải `null`**, nhưng có thể rỗng.
- `@NotEmpty`: container **không `null` và không rỗng**; áp dụng theo kiểu được provider hỗ trợ như `Collection`, `Map`, array, `CharSequence`.
- `@Size(min, max)`: kiểm tra kích thước/độ dài trong khoảng quy định; **`null` vẫn hợp lệ** theo hợp đồng `@Size` chuẩn. Nếu không chấp nhận `null`, thêm `@NotNull` hoặc `@NotEmpty` tùy mục đích.
- `@Valid`: **không phải constraint kiểm tra container có tồn tại**; đây là tín hiệu **cascade** sang đối tượng liên quan khi kiểu/đường duyệt phù hợp.

Ví dụ `@NotEmpty List<String>` yêu cầu kích thước lớn hơn 0. Danh sách `[null]` có một phần tử nên **thỏa `@NotEmpty`**. Nếu phần tử không được phép null, cần thêm `List<@NotNull String>`.

### 2.2. Khác biệt giữa `@Size(min = 1)` và `@NotEmpty`

Với kiểu `List`:

| Input | `@Size(min=1)` | `@NotEmpty` |
| --- | --- | --- |
| `null` | Đạt | Vi phạm |
| `List.of()` | Vi phạm | Vi phạm |
| Danh sách có một phần tử `null` | Đạt | Đạt |
| Danh sách có một phần tử hợp lệ | Đạt | Đạt |

Nếu muốn container **tồn tại và có ít nhất một phần tử**, `@NotEmpty` là cách thể hiện ngắn gọn. Nếu muốn giới hạn cả min/max, kết hợp `@NotNull @Size(min=1, max=20)`. Không cần đặt mọi annotation có thể nghĩ ra; hãy biểu đạt rõ hợp đồng dữ liệu.

### 2.3. Giới hạn kiểu dữ liệu

Không nên gắn `@NotEmpty` lên một DTO kiểu `Address` hay `Optional<String>` rồi mong provider tự hiểu “rỗng”; loại dữ liệu hợp lệ phụ thuộc vào constraint validator được định nghĩa. `@NotEmpty` chuẩn không phải một bộ kiểm tra chung cho tất cả kiểu có method `isEmpty()`.

Với `Optional<String>`, cần phân biệt **đối tượng Optional có null hay không** với **giá trị bên trong Optional có mặt/hợp lệ hay không**. Phần sau giải thích cách dùng constraint trên type argument.

## 3. Ràng buộc phần tử: constraint đặt trong type argument

**Container element constraint** đặt constraint ngay vào kiểu phần tử của container thông qua `TYPE_USE`:

```java
List<@NotNull String> names;
List<@NotBlank String> namesWithText;
List<@Positive Integer> quantities;
Set<@Email String> recipients;
Map<@NotBlank String, @Positive Integer> stockByCode;
```

Đây là các khai báo kiểu để minh họa; muốn compile cần đặt chúng trong class và import các annotation.

Khi bean được validate, provider sẽ dùng **value extractor** lấy ra các phần tử bên trong container rồi kiểm tra constraint gắn với type argument. Đối với loại container chuẩn như `List`, `Iterable`, `Map`, `Optional`, các provider phù hợp như Hibernate Validator đã có những extractor cần thiết.

- `List<@NotNull String>`: mỗi phần tử phải khác `null`. Chuỗi `""` vẫn đạt.
- `List<@NotBlank String>`: mỗi phần tử phải khác `null`, khác `""` và không toàn khoảng trắng.
- `List<@Positive Integer>`: số âm hoặc 0 vi phạm; `null` phần tử vẫn được chấp nhận bởi `@Positive` nên muốn cấm null cần `@NotNull` bổ sung.
- `Map<@NotBlank String, @Positive Integer>`: **key** được kiểm tra bằng `@NotBlank`, **value** bằng `@Positive`; hai vị trí có bộ quy tắc độc lập.

Điều quan trọng: **không cần thêm `@Valid` chỉ để kích hoạt các container element constraint có sẵn**. Ví dụ `List<@NotBlank String>` được provider thực hiện khi Bean Validation kiểm tra property trong bean. `@Valid` dùng cho **kiểm tra sâu vào thuộc tính của bean con**, không phải công tắc bật/tắt `@NotBlank` trên `String`.

### 3.1. Vì sao viết `@NotNull List<@NotNull String>`?

Hai annotation giống nhau về tên nhưng phạm vi khác nhau:

```java
@NotNull
private List<@NotNull String> codes;
```

Tương đương hai điều kiện tách biệt:

1. `codes != null`;
2. với **mọi** phần tử `codes[i]`, `codes[i] != null`.

Vẫn **không yêu cầu danh sách không rỗng** và không yêu cầu chuỗi có ký tự. Để chặt hơn:

```java
@NotEmpty
private List<@NotBlank String> codes;
```

Lúc đó cả container lẫn từng chuỗi phải đáp ứng các quy tắc đã chọn.

### 3.2. Cần phân biệt tên constraint với vị trí annotation

`@NotNull List<String>` không đồng nghĩa `List<@NotNull String>`:

- Trường hợp thứ nhất áp dụng lên **`List`**;
- Trường hợp thứ hai áp dụng lên **`String` trong `List`**.

Cũng không nên coi `@NotEmpty List<String>` và `List<@NotEmpty String>` là tương đương: một bên bắt danh sách có phần tử; bên kia kiểm tra từng `String` không rỗng (trong khi danh sách rỗng vẫn đạt). Khi đọc source code, hãy nhìn **annotation nằm trước hay bên trong dấu `<...>`**.

### 3.3. Một bảng dữ liệu với ví dụ cụ thể

Giả sử property được khai báo:

```java
@NotEmpty
private List<@NotBlank String> names;
```

| Giá trị `names` | Lỗi container | Lỗi phần tử |
| --- | --- | --- |
| `null` | `@NotEmpty` | Không duyệt phần tử |
| `[]` | `@NotEmpty` | Không có phần tử để kiểm tra |
| `[null]` | Không | `@NotBlank` tại phần tử 0 |
| `[""]` | Không | `@NotBlank` tại phần tử 0 |
| `["   "]` | Không | `@NotBlank` tại phần tử 0 |
| `["Alice"]` | Không | Không |
| `["Alice", ""]` | Không | `@NotBlank` tại phần tử 1 |

Tập lỗi được trả về là `Set<ConstraintViolation<T>>`. Thứ tự lặp không được đảm bảo; mỗi constraint thất bại có thể sinh một violation. Với UI, đường dẫn có thể mang index/key của phần tử tùy cấu trúc container và provider.

## 4. @Valid: kiểm tra lồng nhau khác với ràng buộc phần tử đơn giản

Trong Bean Validation, `@Valid` chỉ đạo validation **đi tiếp vào object graph**, chẳng hạn phần tử `OrderLine` có field `sku` với `@NotBlank`.

```java
class OrderLine {
    @NotBlank
    String sku;
}

class OrderBatch {
    @NotEmpty
    List<@NotNull @Valid OrderLine> lines;
}
```

Có ba tầng:

1. `@NotEmpty` kiểm tra `lines` có null/rỗng không.
2. `@NotNull` kiểm tra **mỗi phần tử `OrderLine`** có khác null không.
3. `@Valid` yêu cầu **cascade vào bean `OrderLine`** đang tồn tại để đánh giá constraint của `sku` và các field khác.

### 4.1. Trường hợp nào sinh lỗi?

| Giá trị `lines` | Kết quả |
| --- | --- |
| `null` | Vi phạm `@NotEmpty`; không có phần tử để cascade |
| `[]` | Vi phạm `@NotEmpty` |
| `[null]` | Container đạt; `@NotNull` của phần tử vi phạm; `@Valid` bỏ qua null |
| `[OrderLine(sku="")]` | Container và phần tử đều tồn tại; nested `@NotBlank` của `sku` vi phạm |
| `[OrderLine(sku="A01")]` | Không có violation tương ứng |

**`@Valid` tự nó không yêu cầu phần tử phải khác null.** Vì vậy `List<@Valid OrderLine>` không tương đương `List<@NotNull @Valid OrderLine>`. Dùng thêm `@NotNull` đúng chỗ khi một phần tử null là dữ liệu không hợp lệ.

### 4.2. Không có @Valid thì không tự kiểm tra sâu

Giả sử bạn viết:

```java
@NotEmpty
List<OrderLine> lines;
```

Bean Validation sẽ kiểm tra `lines` không rỗng nhưng không vì thế tự động kiểm tra `OrderLine.sku`. Nếu `lines` chứa các `OrderLine` được dựng từ client và cần ràng buộc nội bộ, thêm `@Valid` tại vị trí cascade thích hợp:

```java
@NotEmpty
List<@Valid OrderLine> lines;
```

Kể từ Jakarta Bean Validation 2.0, đặt `@Valid` trực tiếp ở **type argument** là cách diễn đạt rõ ràng, nhất là với generic lồng nhau và `Map` có key/value. Bạn có thể gặp cách cũ `@Valid List<OrderLine> lines` cho cascade phần tử theo các container tương ứng; tránh đặt `@Valid` **đồng thời trên container và type argument của cùng tuyến cascade**, vì đặc tả khuyến cáo chọn một vị trí để không lặp kiểm tra.

### 4.3. Constraint trên phần tử và cascade không giống nhau

`List<@NotNull OrderLine>` chỉ hỏi phần tử có null không; nó không chạy `@NotBlank` trên `sku`.

`List<@Valid OrderLine>` chạy constraint trong `OrderLine`; nó không tự cấm phần tử null.

`List<@NotNull @Valid OrderLine>` làm cả hai.

`@NotEmpty List<@NotNull @Valid OrderLine>` thêm điều kiện số lượng phần tử của container.

Đây là bốn phạm vi khác nhau và phải chọn theo hợp đồng dữ liệu.

## 5. Map: có thể ràng buộc key, value và chính map

`Map<K,V>` là container có **hai type argument**. Ví dụ:

```java
class Address {
    @NotBlank String street;
}

class ShippingRequest {
    @NotEmpty
    Map<@NotBlank String, @NotNull @Valid Address> addressesByLabel;
}
```

Quy tắc ở từng tầng:

- `@NotEmpty` trên `Map`: map không null và phải chứa ít nhất một entry.
- `@NotBlank` trên key: mỗi nhãn phải có chữ, ví dụ `"home"`, `"office"`; nhãn `""` hoặc `null` không đạt.
- `@NotNull` trên value: mỗi `Address` phải khác null.
- `@Valid` trên value: kiểm tra sâu `Address.street` bằng `@NotBlank`.

Một `Map` có entry `("", new Address(""))` sẽ có ít nhất hai vấn đề về logic: key blank và street blank. Nếu value là `null` thì thiếu object bị bắt bởi `@NotNull`, còn `@Valid` không kiểm tra được field trên đối tượng không tồn tại.

### 5.1. Chỉ kiểm tra container không đủ

`@NotEmpty Map<String,Address>` chỉ yêu cầu có entry; key rỗng, value null và Address có trường sai vẫn có thể qua.

`Map<@NotBlank String,Address>` bắt lỗi key nhưng không đảm bảo value khác null và không cascade.

`Map<String,@Valid Address>` cascade vào value tồn tại nhưng không bắt value null hay key rỗng.

`Map<@NotBlank String,@NotNull @Valid Address>` kết hợp kiểm tra key/value.

Khi yêu cầu cả map phải tồn tại, thêm constraint container như `@NotEmpty`.

### 5.2. Đường dẫn lỗi và map key

Một violation có thể mang path kiểu `addressesByLabel[home].street` cho trường `street` và đường dẫn chỉ phần tử key/value đối với constraint TYPE_USE. Provider có thể hiển thị tên node như `<map key>` hoặc `<map value>`; không hard-code chính xác chuỗi path cho mọi provider.

Thông tin cấu trúc nên sử dụng khi cần là các `Path.Node`, `isInIterable()`, `getKey()`, `getIndex()` và loại node `ElementKind.CONTAINER_ELEMENT`. Đừng mặc định mọi path đều có index số: `List` thường có index, `Map` thường có key, `Set` có thể không xác định vị trí bằng index ổn định.

**Cẩn thận về bảo mật:** key của `Map` hoặc `getInvalidValue()` có thể chứa thông tin nhạy cảm. Khi biến violation thành HTTP response hoặc log, lọc giá trị, dùng thông báo/mã lỗi an toàn và không đưa raw dữ liệu cá nhân ra ngoài.

## 6. Container lồng nhiều tầng và ràng buộc chính xác tại từng tầng

Các generic có thể lồng nhau: `Map<String, List<Address>>`, `List<List<String>>` hoặc `Map<String, Optional<Address>>`. Phải đặt constraint **ở đúng lớp container** muốn kiểm tra.

### 6.1. Map chứa List

```java
class BatchRequest {
    @NotEmpty
    Map<@NotBlank String, @NotEmpty List<@NotBlank String>> codesByGroup;
}
```

Phân tích:

1. `@NotEmpty` bên ngoài kiểm tra `Map` phải khác null và chứa ít nhất một nhóm.
2. `@NotBlank String` trong `Map` kiểm tra tên nhóm (key).
3. `@NotEmpty List<...>` kiểm tra **mỗi danh sách làm value**: danh sách của từng nhóm phải khác null và có phần tử.
4. `List<@NotBlank String>` kiểm tra từng mã nằm trong mỗi danh sách.

Ví dụ `{"primary": ["A", "B"]}` đạt về cấu trúc này; `{"primary": []}` không đạt do value là danh sách rỗng; `{"primary": [""]}` không đạt do phần tử blank; `{"": ["A"]}` không đạt do key rỗng.

Để cascade các object con nhiều tầng:

```java
Map<String, List<@NotNull @Valid Address>> addressesByGroup;
```

Đoạn này giúp provider dùng các value extractor lần lượt đi vào `Map` rồi `List`, sau đó áp dụng `@NotNull` và `@Valid` cho từng `Address`. Không cần khai báo `@Valid` một cách dư thừa tại từng container trung gian khi vị trí type argument đã mô tả chính xác phần tử cần cascade.

### 6.2. Optional: vỏ bọc khác giá trị bên trong

Ví dụ:

```java
@NotNull
Optional<String> nickname;

Optional<@NotBlank String> displayName;
```

Với `nickname`, `@NotNull` đặt trên **đối tượng Optional**: một `Optional.empty()` vẫn là object khác null, nên đáp ứng `@NotNull`. Nếu `nickname == null`, constraint này vi phạm.

Với `displayName`, `@NotBlank` nằm trên **giá trị được Optional bọc**. Hibernate Validator/Jakarta Bean Validation sử dụng extractor của `Optional` để kiểm tra giá trị nội bộ; `Optional.of(" ")` vi phạm, `Optional.of("Alice")` đạt. Với `Optional.empty()`, giá trị trích xuất được xử lý như không có nội dung: một constraint cấm null như `@NotNull`/`@NotBlank` trên type argument sẽ có thể từ chối trường hợp này theo extractor/constraint tương ứng. Nếu `displayName` là tham chiếu `null` chứ không phải một Optional object, không giả định constraint bên trong tự kiểm tra sự hiện diện của vỏ bọc; khai báo quy tắc container riêng khi cần.

Thông thường **không nhất thiết dùng `Optional` làm field DTO hoặc entity**, đặc biệt với Jackson, JPA và binding. Nhiều hệ thống dùng field nullable thông thường trong DTO, còn `Optional` làm kiểu return cho API truy vấn. Chỉ dùng Optional container khi thiết kế dữ liệu và công cụ serialization/binding hỗ trợ nhất quán.

### 6.3. Group và group conversion

Constraint ở container hay phần tử đều nhận thuộc tính `groups`. Ví dụ:

```java
interface Submit {}

class CreateRequest {
    @NotEmpty(groups = Submit.class)
    List<@NotBlank(groups = Submit.class) String> codes;
}
```

Chỉ khi validate với `Submit.class` (hoặc sequence/inheritance tương ứng) thì các constraint nhóm đó mới được thực thi; gọi mặc định `validator.validate(bean)` chọn `Default` và có thể không kiểm tra chúng.

Với cascade `@Valid` vào bean con, có thể dùng `@ConvertGroup` tại vị trí cascade để đổi nhóm từ cha sang con. Đây là cơ chế dành cho **cascaded validation**, không phải cách làm `@NotEmpty` của container tự biến thành constraint cho các phần tử.

## 7. Value extractor: cách Bean Validation nhìn thấy phần tử

Tại sao Bean Validation hiểu `List<@NotNull String>` nhưng có thể không hiểu `Box<@NotNull String>` do ứng dụng tự viết? Vì hệ thống dùng **`ValueExtractor`** để lấy phần tử từ container.

- Container được hỗ trợ sẵn: nhiều dạng `Iterable`/`List`, `Map` (cả key và value), `Optional` và một số dạng khác theo provider.
- Với container custom `Box<T>`, phải có `ValueExtractor` phù hợp cho type argument `T` và đăng ký extractor với provider.
- Khi có nhiều extractor phù hợp gây mơ hồ, cấu hình có thể không xác định được đối tượng cần extract và ném exception.
- Extractor có thể cung cấp index/key hoặc tên node cho `ConstraintViolation#getPropertyPath()`.

Ví dụ khai báo một container custom:

```java
public final class Box<T> {
    private final T item;
    public Box(T item) { this.item = item; }
    public T getItem() { return item; }
}
```

Nếu muốn dùng `Box<@NotBlank String>` và được validator hiểu, phải có extractor tương ứng, chẳng hạn:

```java
import jakarta.validation.valueextraction.ExtractedValue;
import jakarta.validation.valueextraction.ValueExtractor;

public class BoxValueExtractor
        implements ValueExtractor<Box<@ExtractedValue ?>> {

    @Override
    public void extractValues(
            Box<?> original, ValueExtractor.ValueReceiver receiver) {
        receiver.value(null, original.getItem());
    }
}
```

Đây là mã minh họa cần đặt thành các tệp Java đúng tên trong project; không phải phần của chương trình độc lập ở mục 8. Để sử dụng, cấu hình provider đăng ký `BoxValueExtractor` (ví dụ `configuration.addValueExtractor(new BoxValueExtractor())` hoặc cơ chế service loading/đăng ký container phù hợp). Không có extractor cho custom container thì Bean Validation không có cơ chế chuẩn để tự biết phần tử cần kiểm tra.

**Lưu ý:** không nhầm value extraction với `@Valid`: extractor **định vị phần tử**; constraint TYPE_USE kiểm tra giá trị đó; `@Valid` chỉ định có chạy tiếp các constraint bên trong bean con hay không. Ba cơ chế có trách nhiệm khác nhau.

## 8. Ví dụ Java 17+ đầy đủ: container và phần tử sinh lỗi độc lập

Ví dụ dùng Jakarta Bean Validation 3.x với Hibernate Validator 8.x, không cần Spring chạy để hiểu semantics. Mô hình:

- `@NotEmpty List<@NotNull @Valid Line> lines`: container bắt buộc không rỗng; phần tử không null; nested `Line.sku` phải có nội dung.
- `@NotNull List<@NotBlank String> tags`: container bắt buộc tồn tại, có thể rỗng; từng tag không blank.
- `Map<@NotBlank String, @NotNull @Valid Line> byCode`: kiểm tra key, value và nested bean; map **không** bị bắt buộc tồn tại khi không có annotation container.

### 8.1. pom.xml

Tạo thư mục dự án Maven bất kỳ, rồi tạo tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>container-element-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.1.Final</version>
        </dependency>
    </dependencies>
</project>
```

Dependency này kéo theo Jakarta Validation API và các dependency transitive liên quan. Để chạy ví dụ CLI mà không cấu hình Jakarta Expression Language riêng, chương trình chọn `ParameterMessageInterpolator` của Hibernate Validator. Đây là API provider-specific, không phải API Jakarta portable; ứng dụng dùng message expression EL cần cấu hình EL thích hợp.

### 8.2. Tệp ContainerElementDemo.java

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.hibernate.validator.HibernateValidator;
import org.hibernate.validator.messageinterpolation.ParameterMessageInterpolator;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class ContainerElementDemo {

    public static final class Line {
        @NotBlank
        private final String sku;

        public Line(String sku) {
            this.sku = sku;
        }
    }

    public static final class Checkout {
        @NotEmpty
        private final List<@NotNull @Valid Line> lines;

        @NotNull
        private final List<@NotBlank String> tags;

        private final Map<@NotBlank String, @NotNull @Valid Line> byCode;

        public Checkout(
                List<Line> lines,
                List<String> tags,
                Map<String, Line> byCode) {
            this.lines = lines;
            this.tags = tags;
            this.byCode = byCode;
        }
    }

    private static void report(
            String label, Set<? extends ConstraintViolation<?>> errors) {
        System.out.println(label + " -> " + errors.size());
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory = Validation
                .byProvider(HibernateValidator.class)
                .configure()
                .messageInterpolator(new ParameterMessageInterpolator())
                .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            Checkout valid = new Checkout(
                    List.of(new Line("SKU-1")),
                    List.of("sale"),
                    Map.of("main", new Line("SKU-2")));

            List<Line> linesWithErrors = Arrays.asList(
                    new Line(""), null);
            List<String> tagsWithErrors = Arrays.asList(
                    " ", null);

            Map<String, Line> mapWithErrors = new LinkedHashMap<>();
            mapWithErrors.put("", new Line(""));

            Checkout invalid = new Checkout(
                    linesWithErrors, tagsWithErrors, mapWithErrors);

            Checkout emptyContainers = new Checkout(
                    List.of(), List.of(), Map.of());

            Checkout nullContainers = new Checkout(
                    null, null, null);

            report("valid", validator.validate(valid));
            report("invalid", validator.validate(invalid));
            report("empty containers", validator.validate(emptyContainers));
            report("null containers", validator.validate(nullContainers));
        }
    }
}
```

### 8.3. Lệnh chạy

Yêu cầu JDK 17+ và Maven. Chạy tại thư mục chứa `pom.xml` và `ContainerElementDemo.java`.

Bash (Linux/macOS):

```bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
CP="$(cat classpath.txt)"
javac -encoding UTF-8 -cp "$CP" ContainerElementDemo.java
java -cp ".:$CP" ContainerElementDemo
```

PowerShell (Windows):

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$cp = (Get-Content -Raw classpath.txt).Trim()
javac -encoding UTF-8 -cp $cp ContainerElementDemo.java
java -cp ".;$cp" ContainerElementDemo
```

Stdout kỳ vọng (không tính các dòng log/cảnh báo provider/Maven nếu môi trường in thêm):

```text
valid -> 0
invalid -> 6
empty containers -> 1
null containers -> 2
```

Giải thích từng trường hợp:

- **`valid -> 0`:** tất cả container và mọi phần tử/nested bean đều thỏa constraint.
- **`invalid -> 6`:** `lines` có một bean `Line(sku="")` gây một lỗi `@NotBlank` và một phần tử null gây một lỗi `@NotNull`; `tags` có chuỗi trắng và phần tử null gây hai lỗi `@NotBlank`; `byCode` có key blank gây một lỗi `@NotBlank` và bean `Line(sku="")` gây một lỗi nested `@NotBlank`. Tổng `2 + 2 + 2 = 6`.
- **`empty containers -> 1`:** `lines=[]` vi phạm `@NotEmpty`; `tags=[]` hợp lệ vì `@NotNull` không bắt buộc có phần tử; `byCode={}` hợp lệ vì không có constraint container.
- **`null containers -> 2`:** `lines=null` vi phạm `@NotEmpty`, `tags=null` vi phạm `@NotNull`; `byCode=null` không có constraint áp dụng lên chính map nên không bị từ chối bởi riêng bộ constraint này.

Để quan sát chi tiết vị trí lỗi, có thể in `violation.getPropertyPath()`, `violation.getConstraintDescriptor().getAnnotation().annotationType().getSimpleName()` và duyệt các `Path.Node`. Không khẳng định biểu diễn đường dẫn của từng element giống nhau trên mọi provider, và không dựa vào thứ tự của `Set`.

### 8.4. Vì sao không cần @Valid ở mọi nơi?

`@NotBlank` trong `List<@NotBlank String>` đã là constraint TYPE_USE, nên validator lấy phần tử `String` và kiểm tra trực tiếp. Nó **không cần `@Valid`**.

`Line.sku` lại là **property của một bean con**: cần `@Valid` trên type argument `Line` hoặc một tuyến cascade tương đương để đi vào `Line`. Trước khi chạy ví dụ, cần nhớ `@Valid` không cấm null, do đó `@NotNull` trên phần tử và `@Valid` thường được phối hợp.

### 8.5. Mở rộng bài thực hành

Thay đổi lần lượt một dòng để tự thấy sự khác biệt:

1. Bỏ `@NotEmpty` trên `lines`: `emptyContainers` từ một lỗi thành không lỗi, còn các lỗi phần tử của `invalid` vẫn tồn tại.
2. Bỏ `@NotNull` trên type argument `Line` trong `lines`: phần tử null không còn bị constraint trực tiếp bắt lỗi; `@Valid` vẫn bỏ qua null.
3. Bỏ `@Valid` trên `Line`: nội dung `sku` sẽ không được duyệt chỉ nhờ `@NotNull` và `@NotEmpty`.
4. Thêm `@NotEmpty` lên `byCode`: map rỗng hoặc null cũng phải bị từ chối.
5. Thay `@NotNull List<@NotBlank String> tags` bằng `@NotEmpty List<@NotBlank String> tags`: `tags=[]` chuyển thành không hợp lệ.

Những thay đổi này hữu ích để phân biệt rõ **ràng buộc trên container**, **ràng buộc trên phần tử**, và **cascade validation**.

## 9. Gắn với Spring MVC và data binding

Trong Spring MVC, dữ liệu JSON/form có thể bind vào DTO rồi được Bean Validation kiểm tra khi controller khai báo `@Valid` hoặc `@Validated` ở tham số phù hợp. Đây là nơi việc chọn đúng tầng constraint trở nên quan trọng: request có danh sách, danh sách có phần tử và từng phần tử có field.

DTO minh họa cho API JSON:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

public class CreateOrderRequest {

    @NotEmpty
    private List<@NotNull @Valid LineRequest> lines;

    public List<LineRequest> getLines() {
        return lines;
    }

    public void setLines(List<LineRequest> lines) {
        this.lines = lines;
    }

    public static class LineRequest {
        @NotBlank
        private String sku;

        public String getSku() {
            return sku;
        }

        public void setSku(String sku) {
            this.sku = sku;
        }
    }
}
```

Đây là DTO tích hợp (tệp riêng `CreateOrderRequest.java`) chứ không thuộc chương trình độc lập mục 8. Từng dòng hàng phải có `sku` không blank, phần tử dòng hàng không được null, và danh sách phải không rỗng.

Controller minh họa trong một `@RestController` có các import Spring tương ứng:

```java
@PostMapping("/orders")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateOrderRequest request,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        var codes = bindingResult.getFieldErrors().stream()
                .map(e -> e.getField() + ":" + e.getCode())
                .toList();
        return ResponseEntity.badRequest().body(codes);
    }

    return ResponseEntity.ok().build();
}
```

Luồng xử lý cần hiểu:

1. `HttpMessageConverter`/Jackson deserialize JSON thành DTO; lỗi JSON sai cú pháp hoặc sai kiểu có thể xảy ra **trước** khi gọi Bean Validation.
2. Khi `@Valid` trên tham số được Spring xử lý theo cơ chế MVC phù hợp, validator kiểm tra DTO gốc, constraint container, phần tử, rồi cascade theo `@Valid` type argument.
3. `BindingResult` nếu đặt ngay sau DTO tương ứng có thể chứa lỗi field. Đường dẫn field có thể có index như `lines[0].sku` hoặc dấu chỉ phần tử container.
4. Khi validation đạt, service vẫn phải kiểm tra SKU có tồn tại, được bán, đủ tồn kho, phân quyền, giới hạn nghiệp vụ. Bean Validation chỉ giải quyết các điều kiện nó được cấu hình.

**Đừng nhầm `@Valid` trên controller với `@Valid` trên type argument.** Thứ nhất là tín hiệu cho Spring/MVC thực hiện validation object đầu vào; thứ hai chỉ tuyến cascade sang các bean nằm trong container. Cần xem cả **điểm kích hoạt** và **đường đi sâu**.

### 9.1. Form binding và JSON có khác nhau?

Có thể khác ở bước tạo dữ liệu:

- JSON `{"lines": null}` hoặc field vắng mặt thường tạo `lines == null` (tùy deserializer/constructor/default), nên `@NotEmpty` sẽ bắt lỗi.
- JSON `{"lines": []}` tạo list rỗng, `@NotEmpty` cũng bắt lỗi.
- JSON `{"lines": [null]}` tạo list một phần tử null, container `@NotEmpty` đạt nhưng constraint `@NotNull` trên phần tử thất bại.
- JSON `{"lines": [{"sku": ""}]}` có phần tử khác null; nested `@NotBlank` của `sku` thất bại nếu cascade hoạt động.

Với form parameter dạng `lines[0].sku`, Spring binder/auto-grow collection và cấu hình binding ảnh hưởng tới việc tạo phần tử và xử lý index, khác với Jackson deserialize JSON. Hãy kiểm thử con đường HTTP thật, không chỉ dùng `Validator` độc lập và giả định JSON/form luôn cho cùng object graph.

### 9.2. Validation groups trong Spring

`@Validated(SomeGroup.class)` của Spring có thể chọn group cho DTO. Constraint trên container và type argument đều có `groups`; nếu chỉ validate group `Create` mà constraint thuộc `Default`, chúng không tự động chạy trừ khi có khai báo sequence/inheritance/conversion phù hợp.

Khi cascade sang bean con, group propagation hoặc `@ConvertGroup` có thể làm nhóm ở bean con khác nhóm kiểm tra container. Cần kiểm thử chính sách nhóm theo tác vụ Create/Update, đặc biệt nếu có optional/partial update và các container lồng nhau.

### 9.3. Bảo vệ khỏi input độc hại

`@NotEmpty` chỉ quy định ít nhất một phần tử, **không chặn danh sách cực lớn**. Dùng `@Size(max=...)` hoặc giới hạn số phần tử theo API, cấu hình giới hạn kích thước JSON/form, và kiểm tra tổng số đối tượng lồng nhau để tránh lạm dụng CPU/bộ nhớ.

Constraint TYPE_USE có thể đánh giá từng phần tử; lồng nhiều tầng cùng lượng dữ liệu lớn tạo chi phí validation đáng kể. Đừng dùng kết quả validation để bỏ qua giới hạn request size, rate limit, database constraints hoặc authorization.

## 10. Các bẫy hay gặp

| Lỗi phổ biến | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| `@NotEmpty List<String>` được cho là kiểm tra String không blank | Chỉ kiểm tra kích thước danh sách | Thêm `List<@NotBlank String>` |
| `List<@NotNull String>` được cho là bắt buộc danh sách có phần tử | Constraint chỉ gắn trên từng element | Thêm `@NotEmpty` cho list |
| `List<@Valid Address>` được cho là cấm element null | Cascade bỏ qua tham chiếu null | Dùng `List<@NotNull @Valid Address>` |
| `@NotNull List<@Valid Address>` được cho là cấm danh sách rỗng | `@NotNull` chỉ cấm container null | Thêm `@NotEmpty` hoặc `@Size(min=1)` |
| Container có đối tượng con nhưng field trong con không báo lỗi | Chưa có cascade `@Valid` | Đặt `@Valid` ở type argument/tuyến cascade hợp lệ |
| Đặt `@Valid` cả trên List và type argument cùng tuyến | Có thể cấu hình cascade dư thừa | Chọn một vị trí, ưu tiên type argument |
| `Map<@NotBlank String,Address>` vẫn có Address null | Key constraint không kiểm tra value | Thêm `@NotNull` ở value type argument |
| Chỉ dùng `@Valid` trên Map value nhưng map rỗng vẫn đạt | Cascade không bắt map có phần tử | Thêm constraint container nếu cần |
| `@Size(min=1) List<?>` vẫn chấp nhận null | `@Size` cho phép null | Kết hợp `@NotNull` hoặc `@NotEmpty` |
| Container custom với `Box<@NotBlank String>` không hoạt động | Thiếu ValueExtractor phù hợp | Đăng ký custom `ValueExtractor` và test |
| Có annotation nhưng HTTP không trả validation errors | Validation chưa được Spring kích hoạt, thiếu provider hoặc sai namespace | Thêm provider và `@Valid`/`@Validated` đúng nơi |
| JSON có phần tử null gây lỗi binding khác mong đợi | Deserialize/type construction diễn ra trước validation | Tách lỗi đọc JSON khỏi violation constraint |
| Dùng `validateProperty` rồi nghĩ nested @Valid được chạy | API này không thực hiện cascade | Dùng `validate(rootBean)` khi cần kiểm tra object graph |
| Đếm số lỗi mà bỏ qua index/key | Lỗi trong list/map có vị trí riêng | Đọc `Path.Node`, gắn lỗi đúng phần tử |
| Cho rằng Bean Validation tự kiểm tra quan hệ DB/ownership | Constraint chỉ áp dụng rule đã khai báo | Kiểm tra nghiệp vụ trong service/transaction |
| Log toàn bộ vi phạm gồm input người dùng | Có thể lộ dữ liệu nhạy cảm | Log mã lỗi/path, ẩn raw values |

### 10.1. Phân biệt với class-level/cross-field constraint

Cả container-level và element-level đều chưa chắc đủ cho rule liên quan **nhiều** phần tử. Ví dụ “danh sách mã hàng không được trùng nhau” hoặc “tổng số lượng tất cả dòng không vượt quá hạn mức” cần validation ở tầng tập hợp/bean hoặc nghiệp vụ. `@NotEmpty` và `@NotNull` không phát hiện trùng lặp hay tính tổng.

Có thể viết custom constraint áp dụng lên list, class-level constraint cho DTO hoặc kiểm tra ở service. Đừng dùng regex của từng element để diễn đạt quy tắc phụ thuộc các phần tử khác.

### 10.2. Kiểm thử cần có

Viết test rõ ràng cho ít nhất các trường hợp sau:

1. Container null, rỗng, có một phần tử, nhiều phần tử.
2. Phần tử null, chuỗi rỗng, chuỗi whitespace, đối tượng con có field invalid.
3. `List` hợp lệ nhưng bean nested invalid: chỉ lỗi xuất hiện khi có cascade phù hợp.
4. `Map` có key invalid, value null, value có field invalid.
5. Generic lồng nhiều tầng: list rỗng ở tầng trong, phần tử invalid ở tầng sâu.
6. `Optional.empty()`, `Optional.of(...)` nếu dữ liệu nghiệp vụ thực sự dùng Optional.
7. Validation group mặc định và group custom; khi có `@ConvertGroup`, test đường cascade.
8. `getPropertyPath()`, index/key và cách map lỗi sang UI.
9. Input JSON/form lỗi kiểu, thiếu property, container cực lớn và giới hạn payload.
10. Schema/provider upgrade: bảo đảm bộ value extractor và metadata constraint được dùng như dự kiến.

**Không assert thứ tự duyệt của `Set<ConstraintViolation<?>>`.** Muốn kết quả test ổn định, sắp xếp theo path/constraint hoặc kiểm tra tập hợp khóa bất kể thứ tự.

## 11. Quy trình chọn constraint theo ba tầng

Khi thiết kế một property dạng container:

1. **Đối tượng container có được phép null không?** Nếu không, đặt `@NotNull` hoặc constraint mạnh hơn như `@NotEmpty` trên chính property.
2. **Container có được phép rỗng không?** Nếu không, chọn `@NotEmpty` hoặc `@Size(min=1)` cộng điều kiện cấm null phù hợp.
3. **Từng phần tử cần tuân theo quy tắc gì?** Đặt constraint bên trong type argument, ví dụ `List<@NotBlank String>` hoặc `Map<@NotBlank String,@Positive Integer>`.
4. **Phần tử có được phép null không?** Nếu không, đặt `@NotNull` trên type argument (nhiều constraint như `@NotBlank` đã tự cấm null).
5. **Phần tử là bean có constraint ở field bên trong?** Thêm `@Valid` ở type argument để cascade tới bean con.
6. **Container có nhiều tầng?** Đặt constraint ở **mỗi tầng cần quản lý**; không để annotation ở Map ngoài khi ý định là bắt List ở trong không rỗng.
7. **Có group hoặc container custom?** Xác định nhóm chạy, tuyến cascade, `ValueExtractor` và test trên provider đang dùng.
8. **Dữ liệu đến từ Spring MVC?** Bảo đảm validation được kích hoạt sau binding, xử lý lỗi chính xác và kiểm tra nghiệp vụ độc lập.

**Ghi nhớ một câu:** ràng buộc **container** hỏi “cái hộp có tồn tại, có đủ phần tử không?”; ràng buộc **container element** hỏi “từng thứ trong hộp có hợp lệ không?”; `@Valid` hỏi “có tiếp tục kiểm tra các thuộc tính của object bên trong không?”. Một API an toàn thường cần kết hợp cả ba thay vì chọn một và mặc định hai điều còn lại đã được đảm bảo.

### Tài liệu tham khảo

- Jakarta Bean Validation 3.0 Specification — Container element constraints, cascaded validation, value extraction: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Hibernate Validator 8 Reference Guide — Container element constraints và Value extraction: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Jakarta Validation API — `@Valid`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/valid
- Jakarta Validation API — `@NotEmpty`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/notempty
- Spring Framework — Bean Validation integration: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC — Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring MVC — `@RequestBody`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
