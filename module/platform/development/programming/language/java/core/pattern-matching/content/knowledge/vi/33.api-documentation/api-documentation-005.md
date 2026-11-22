# Tài liệu hóa record component trong Java: Javadoc, contract và API rõ ràng (Java 21)

## 1. Vì sao record component cần tài liệu riêng?

Một record biểu diễn một tập **giá trị cấu thành trạng thái** bằng danh sách component trong phần header:

```java
public record Point(int x, int y) {}
```

Java cung cấp constructor chuẩn (canonical constructor), accessor `x()`/`y()` và các phương thức `equals`, `hashCode`, `toString` dựa trên các component. Tuy nhiên, nhìn tên `x` và `y` không cho biết hệ tọa độ, đơn vị đo, miền hợp lệ, khả năng nhận `null` hoặc ý nghĩa của một thay đổi dữ liệu.

Với API công khai, **component không chỉ là field để chứa dữ liệu**. Nó đồng thời ảnh hưởng đến:

- Tham số và thứ tự của canonical constructor;
- Accessor có cùng tên component;
- Hình dạng của record pattern trong Java 21;
- `equals`/`hashCode` và cách biểu diễn `toString` được sinh mặc định;
- Schema mà một số thư viện serialization, reflection hoặc mapping công khai;
- Tính tương thích khi thêm, xóa, đổi tên hoặc đổi kiểu component.

Do đó, tài liệu của record cần trả lời **“giá trị này có nghĩa gì, ai được tạo, được đọc và được phép giả định điều gì?”** chứ không đơn thuần lặp lại tên và kiểu Java.

Ví dụ thiếu thông tin:

```java
public record Price(long amount, String currency) {}
```

`amount` là đồng, xu, cent hay đơn vị minor currency? Có chấp nhận số âm? `currency` có thể `null` không? Có bắt buộc ISO 4217 không? `"usd"` có được chuẩn hóa thành `"USD"` không? Người dùng API không thể suy ra các chi tiết ấy từ chữ ký.

**Mục tiêu bài học:** viết Javadoc đúng vị trí bằng `@param` cho record component; ghi rõ ý nghĩa, đơn vị, invariant, nullability, normalization và ownership; tài liệu hóa compact constructor, accessor tùy biến, generic component và record pattern; dùng công cụ `javadoc` để phát hiện lỗi và kiểm tra HTML được sinh.

Bài thuộc mục **API và tài liệu** của Java Core Pattern Matching. `record` là tính năng chuẩn từ **Java 16** (JEP 395), còn record patterns và pattern matching cho `switch` chính thức từ **Java 21** (JEP 440, JEP 441). Chương trình đầy đủ dùng **JDK 21+**; việc tạo tài liệu Javadoc áp dụng cho cả record không sử dụng pattern matching.

## 2. Cú pháp cốt lõi: `@param` trên Javadoc của record

Đối với record, cách quen thuộc và được hỗ trợ bởi công cụ **standard doclet** là đặt Javadoc **ngay trước khai báo `record`**, rồi dùng `@param` với **đúng tên từng component**:

```java
/**
 * Một tọa độ trên mặt phẳng tính bằng mét.
 *
 * @param x hoành độ, tính bằng mét; phải không âm
 * @param y tung độ, tính bằng mét; phải không âm
 */
public record Point(int x, int y) {
    public Point {
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException(
                "Coordinates must be non-negative");
        }
    }
}
```

Trong ví dụ:

- Phần mô tả đầu giải thích **ý nghĩa tổng thể của record**.
- `@param x` giải thích component `x`, không cần tạo một field Javadoc riêng.
- `@param y` giải thích component `y`.
- Compact constructor bảo đảm đúng lời hứa **không âm**.

`@param` xuất hiện tại Javadoc của **type declaration**, nhưng với record, standard doclet sử dụng nó để thể hiện thông tin các component. Đây là cách viết trọng tâm cần ghi nhớ. Không viết `@return` trực tiếp trên Javadoc của `record`: `@return` dành cho method, không dành cho type.

**Đúng tên là bắt buộc:** với `record Point(int x, int y)`, viết `@param length` thay cho `@param x` là sai đối tượng tham chiếu và có thể bị doclint cảnh báo. Khi đổi tên một component, phải cập nhật `@param` tương ứng.

### Một record chỉ cần mô tả được contract, không cần dài dòng

Ví dụ ngắn nhưng hữu ích:

```java
/**
 * Mã khách hàng đã được chuẩn hóa để so sánh theo giá trị.
 *
 * @param value mã khách hàng không null/blank, được loại khoảng trắng
 *              hai đầu khi khởi tạo; case được giữ nguyên
 */
public record CustomerId(String value) {
    public CustomerId {
        value = java.util.Objects.requireNonNull(value, "value").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("Blank customerId");
        }
    }
}
```

Ở đây cách xử lý thực tế đúng với tài liệu: `strip()`, không `toUpperCase()`. Nếu business quyết định mã không phân biệt chữ hoa/chữ thường, phải sửa cả implementation và contract; không thể chỉ sửa câu mô tả.

### Đừng đặt bình luận thường rồi tưởng là Javadoc

```java
// Mã tiền tệ.
public record Currency(String code) {}
```

Bình luận `//` có thể giúp người đọc source, nhưng **không phải Javadoc** được xử lý như documentation comment cho API. Hãy dùng dạng `/** ... */` trước khai báo record khi muốn tạo trang tài liệu chính thức.

## 3. Những thuộc tính cần nêu cho mỗi component

Một Javadoc tốt không nhất thiết có đủ mọi mục, nhưng phải làm rõ **những hợp đồng mà người dùng không thể suy ra từ kiểu**.

| Khía cạnh | Câu hỏi cần trả lời | Ví dụ mô tả |
| --- | --- | --- |
| Ý nghĩa domain | Component đại diện cho điều gì? | `customerId` là mã định danh trong hệ thống bán hàng |
| Đơn vị đo | Số này đo theo đơn vị nào? | `minorUnits` là đơn vị nhỏ nhất của tiền tệ |
| Miền hợp lệ | Có được âm, bằng 0, ngoài ngưỡng không? | `quantity >= 1` |
| Nullability | `null` được phép và có nghĩa gì? | `address` bắt buộc; `notes` có thể null nghĩa là chưa nhập |
| Chuẩn hóa | Constructor có biến đổi input không? | `currency` được `strip()` và viết hoa bằng `Locale.ROOT` |
| Tính bất biến | Component có giữ tham chiếu mutable không? | `lines` là bản sao không cho sửa cấu trúc |
| Cấu trúc collection | List có thể rỗng, có phần tử null không? | `lines` không rỗng, phần tử non-null |
| Equality/ordering | Thứ tự hoặc scale có quan trọng không? | `List.equals` quan tâm thứ tự; `BigDecimal.equals` quan tâm scale |
| Version và tương thích | Nếu thêm component thì API đổi ra sao? | Có thể thay đổi ctor, accessor và record patterns |
| Bảo mật | Có thông tin nhạy cảm không? | Không log token hoặc dựa vào `toString()` để che dữ liệu |

**Không bịa các lời hứa.** `record` chỉ bảo đảm field tương ứng component là final theo cấu trúc, **không** tạo deep immutability. Nếu component là `List<MutableItem>` và chỉ dùng `List.copyOf`, các phần tử có thể bị sửa qua tham chiếu khác. Javadoc không nên ghi “toàn bộ object graph immutable” nếu không có cơ chế bảo vệ thật.

### Unit là phần contract, không phải chi tiết phụ

So sánh:

```java
/** @param amount số tiền */
record Money(long amount) {}
```

với:

```java
/**
 * Số tiền không âm theo đơn vị nhỏ nhất của loại tiền.
 *
 * @param minorUnits số đơn vị nhỏ nhất, phải từ 0 trở lên
 * @param currency mã tiền tệ ba chữ cái được viết hoa khi khởi tạo
 */
record Money(long minorUnits, String currency) {}
```

Đoạn thứ hai ngăn hiểu sai giữa 1.000 đơn vị lớn và 1.000 đơn vị nhỏ. Nhưng một regex ba chữ cái **không đủ để xác thực ISO 4217**; nếu implementation chỉ kiểm tra `[A-Z]{3}`, tài liệu phải nói chính xác là “ba chữ cái” chứ không tuyên bố tất cả giá trị là mã tiền tệ ISO hợp lệ.

## 4. Ghi rõ nullability: contract, không chỉ annotation

Java cho phép truyền `null` vào component kiểu reference của record nếu constructor không cấm:

```java
record RawContact(String email, String phone) {}

RawContact input = new RawContact(null, null); // Hợp lệ về cú pháp.
```

Nếu domain cần `email`, tài liệu nên nói **không được null** và constructor cần kiểm tra:

```java
/**
 * Thông tin liên hệ đã kiểm tra.
 *
 * @param email địa chỉ email bắt buộc, không null/blank
 * @param phone số điện thoại tùy chọn; null nghĩa là chưa cung cấp
 */
record Contact(String email, String phone) {
    Contact {
        email = java.util.Objects.requireNonNull(email, "email").strip();
        if (email.isEmpty()) {
            throw new IllegalArgumentException("Blank email");
        }
    }
}
```

Cần phân biệt:

- **Component type:** `String` tự nó không biểu thị non-null.
- **Javadoc contract:** câu mô tả truyền đạt kỳ vọng và ý nghĩa nghiệp vụ.
- **Constructor validation:** thực thi kỳ vọng khi tạo object.
- **Annotation:** `@Nullable`/`@NonNull` từ thư viện có thể giúp tooling phân tích, nhưng Java không có một annotation non-null chung có hiệu lực runtime cho mọi ứng dụng.

Khi một component nullable, hãy nói **null nghĩa là gì**. “Có thể null” nhưng không có ngữ nghĩa thường khiến caller phải đoán. Nếu việc thiếu dữ liệu có nhiều trạng thái nghiệp vụ khác nhau, nên cân nhắc enum, sealed variants hoặc kiểu kết quả thay vì chỉ một `null` mơ hồ.

### Record pattern không tự loại bỏ null component

```java
if (value instanceof RawContact(var email, var phone)) {
    // email và phone có kiểu String, nhưng vẫn có thể là null.
}
```

`var email` ràng buộc giá trị component, kể cả `null`. Với nested record pattern:

```java
record Customer(RawContact contact) {}

if (value instanceof Customer(RawContact(var email, var phone))) {
    // Chỉ khớp nếu Customer.contact khác null và là RawContact.
}
```

Nếu `contact == null`, pattern con `RawContact(...)` không khớp và thân `if` không chạy. Nhưng nếu contact không-null mà `email == null`, pattern vẫn khớp; `email` có thể null. Vì vậy tài liệu component rất quan trọng cho code dùng record patterns: **kiểu tĩnh của biến pattern chưa phải lời hứa về non-null của giá trị**.

## 5. Tài liệu hóa validation và normalization trong canonical constructor

Javadoc `@param` trên record mô tả **các component và hợp đồng tổng thể**. Nếu có compact canonical constructor/constructor tường minh, hãy mô tả thêm những hành vi tạo đối tượng quan trọng và exception được ném.

Ví dụ:

```java
/**
 * Mã sản phẩm được chuẩn hóa để so sánh theo giá trị.
 *
 * @param code mã sau chuẩn hóa, chữ hoa ASCII/chữ số/dấu gạch nối;
 *             phải dài từ 2 tới 20 ký tự
 */
public record ProductCode(String code) {

    /**
     * Chuẩn hóa mã đầu vào trước khi lưu trạng thái.
     *
     * @throws NullPointerException nếu code là null
     * @throws IllegalArgumentException nếu mã sau chuẩn hóa sai định dạng
     */
    public ProductCode {
        code = java.util.Objects.requireNonNull(code, "code")
            .strip()
            .toUpperCase(java.util.Locale.ROOT);
        if (!code.matches("[A-Z0-9-]{2,20}")) {
            throw new IllegalArgumentException("Invalid product code");
        }
    }
}
```

**Ghi nhớ về vị trí tag:**

- `@param code` trên Javadoc **của record** mô tả component.
- `@throws` thuộc Javadoc **của constructor hoặc method** có thể ném exception.
- Nếu ghi tài liệu riêng cho một **canonical constructor tường minh có danh sách tham số**, `@param` ở Javadoc của constructor mô tả tham số constructor đó. Với compact constructor, danh sách tham số được suy ra từ record header; tránh lặp câu mô tả khác ý với `@param` ở type.
- Đừng thêm `@throws` vào Javadoc của record type rồi cho rằng chuẩn doclet sẽ xem nó là tag của constructor: `@throws` có ngữ cảnh method/constructor.

### Compact constructor không gán trực tiếp component field

Trong `public ProductCode { ... }`, tham số `code` được chuẩn hóa. Khi constructor kết thúc bình thường, compiler gán kết quả cuối của tham số cho component field. Không viết `this.code = code` trong thân compact constructor. Việc mô tả normalization cần phản ánh **giá trị được lưu**, không chỉ “input ban đầu”.

### Constructor có thể nhận input khác với giá trị accessor trả về

Nếu gọi:

```java
var product = new ProductCode(" ab-12 ");
System.out.println(product.code()); // AB-12
```

thì người dùng API có quyền kỳ vọng accessor trả **mã đã chuẩn hóa**. Vì vậy `@param code` nên đề cập normalization; Javadoc của explicit accessor (nếu có) cũng phải phản ánh kết quả sau chuẩn hóa.

## 6. Accessor được sinh và accessor khai báo tường minh

Record có accessor cùng tên component:

```java
record Range(int lower, int upper) {}
// Các accessor: lower() và upper().
```

Đây **không phải** JavaBean setter/getter theo tên `getLower()`. Người đọc tài liệu cần biết accessor mà họ sẽ gọi là `lower()`, và giá trị trả về có cùng kiểu đã công bố.

**Nếu accessor được sinh ngầm**, không cần tự viết một method chỉ để gắn Javadoc lặp lại. Tập trung mô tả component ngay trong `@param` của record và kiểm tra HTML do `javadoc` tạo.

Khi **khai báo accessor tường minh** vì có hành vi đáng giải thích, viết Javadoc của method đó, dùng `@return` đúng ngữ cảnh:

```java
/**
 * Tên địa điểm đã được chuẩn hóa bằng cách loại khoảng trắng hai đầu.
 *
 * @param name tên bắt buộc; sẽ được chuẩn hóa bằng strip()
 */
public record Place(String name) {
    public Place {
        name = java.util.Objects.requireNonNull(name, "name").strip();
        if (name.isBlank()) {
            throw new IllegalArgumentException("Blank place name");
        }
    }

    /**
     * Trả tên địa điểm đã được chuẩn hóa.
     *
     * @return tên không null và không blank
     */
    public String name() {
        return name;
    }
}
```

Accessor tùy biến phải có đúng chữ ký phù hợp với component (ở đây `public String name()`). Không nhầm record component với một field có thể tự ý che giấu/sửa qua accessor. Đặc tả record mong đợi các accessor phản ánh component một cách nhất quán; đặc biệt nếu dùng record pattern, các accessor được dùng để deconstruct.

**Lưu ý hiệu năng:** không đặt I/O nặng hoặc side effect nghiệp vụ trong accessor chỉ vì muốn “tự tính khi đọc”, vì `Record(var x)` có thể gọi accessor. Nếu accessor ném exception trong quá trình record pattern matching, Java 21 có quy tắc `MatchException` với cause gốc. Tài liệu công khai và thiết kế API phải coi accessor như đường đọc dữ liệu có contract đáng tin cậy.

## 7. Tài liệu hóa collection component: ownership và bất biến nông

Một record có component `List<T>` có thể dễ gây hiểu lầm. Xét:

```java
record UnsafeOrder(java.util.List<String> lines) {}
```

Field `lines` là final, nhưng caller có thể:
- Sửa list đầu vào sau khi tạo record;
- Sửa list lấy từ `lines()` nếu list mutable;
- Làm `equals`/`hashCode` của record thay đổi khi danh sách thay đổi.

Vì vậy cần xác định ownership trong tài liệu, rồi cài đặt đúng:

```java
/**
 * Ảnh chụp các mã SKU theo đúng thứ tự nhận vào.
 *
 * @param items danh sách không null, không rỗng và không có phần tử null;
 *              được sao chép thành danh sách không cho sửa cấu trúc
 */
record SkuSnapshot(java.util.List<String> items) {
    SkuSnapshot {
        items = java.util.List.copyOf(
            java.util.Objects.requireNonNull(items, "items"));
        if (items.isEmpty()) {
            throw new IllegalArgumentException("Empty items");
        }
    }
}
```

Với `String` immutable, danh sách đã sao chép giữ một snapshot có cấu trúc ổn định và không lộ list mutable qua accessor mặc định.

**Không mô tả `List.copyOf` là deep copy.** Nếu component là `List<MutableAddress>`, phần tử vẫn mutable dù list không cho thêm/xóa. Javadoc cần nói rõ mức bảo vệ thực sự và cân nhắc dùng immutable value object cho phần tử.

### Mảng và equality

`record Bytes(byte[] data)` nguy hiểm hơn: array mutable và `equals`/`hashCode` mặc định của record dùng equality của mảng theo tham chiếu, không so nội dung byte. Nếu domain cần value semantics theo nội dung, phải thiết kế clone lúc nhận/trả và override equality/hash tương thích, hoặc chọn một wrapper khác. Javadoc không thể tự biến array thành immutable.

### Thứ tự phần tử có ý nghĩa hay không?

`List.equals` so sánh theo thứ tự. Nếu domain xem hai danh sách cùng phần tử khác thứ tự là tương đương, hãy dùng mô hình phù hợp (chẳng hạn một tập hoặc chuẩn hóa thứ tự) và nêu rõ. Không thể chỉ ghi “không có thứ tự” trong `@param` mà vẫn giữ một List có equality theo thứ tự và coi như contract đã được thực thi.

## 8. Tài liệu hóa generic record, enum và component type phức tạp

Record hỗ trợ generics:

```java
/**
 * Một kết quả phân trang đã xử lý.
 *
 * @param <T> kiểu phần tử của danh sách kết quả
 * @param items danh sách phần tử, không null; thứ tự được giữ nguyên
 * @param total tổng số kết quả, phải không âm
 */
public record Page<T>(java.util.List<T> items, long total) {
    public Page {
        items = java.util.List.copyOf(
            java.util.Objects.requireNonNull(items, "items"));
        if (total < 0) {
            throw new IllegalArgumentException("Negative total");
        }
    }
}
```

Ở đây **`@param <T>`** mô tả type parameter còn **`@param items`** mô tả record component. Hai thứ khác nhau. Một Javadoc tốt cần mô tả cả hai nếu tên `T` không tự đủ nghĩa.

Với `Page<T>`:
- `List.copyOf` không chấp nhận element null;
- Nó không làm phần tử kiểu `T` thành immutable;
- `total` là số kết quả tổng, không nhất thiết là số item trên trang;
- Nếu cần invariant `items.size() <= total`, hãy **thực thi** trong constructor trước khi ghi nó vào tài liệu.

Một component enum có thể tự nói lên phần lớn miền giá trị:

```java
enum State { CREATED, PAID, CANCELLED }
/** @param state trạng thái đơn, bắt buộc khác null */
record OrderStatus(State state) {}
```

Tuy nhiên Javadoc `@param state` **không tự ngăn** `new OrderStatus(null)`. Nếu contract là non-null, phải có validation hoặc quy ước có cơ chế kiểm tra thích hợp.

### Annotation và công cụ khác

Một annotation ở record component có thể áp dụng cho FIELD, METHOD, PARAMETER hoặc RECORD_COMPONENT tùy `@Target` của annotation đó; các trường hợp được lan truyền tới thành viên tạo ra có quy tắc riêng. **Không giả định mọi annotation đều được lan truyền đến mọi nơi**, hoặc một `@NotNull` từ thư viện sẽ luôn tạo runtime check. Hãy kiểm tra toolchain thực tế của ứng dụng và giữ Javadoc với constructor nhất quán.

## 9. Record patterns làm tài liệu component quan trọng hơn

Java 21 cho phép:

```java
record GeoPoint(double latitude, double longitude) {}

if (value instanceof GeoPoint(var lat, var lon)) {
    System.out.println(lat + ", " + lon);
}
```

Component ở header quyết định **thứ tự** trích xuất. Nếu `latitude` và `longitude` cùng kiểu `double`, compiler không phát hiện việc một người vô tình đọc `lon` như vĩ độ trong logic khác. Tài liệu phải nêu:
- `latitude` là **vĩ độ** theo độ, miền hợp lệ từ -90 đến 90 nếu constructor thực thi;
- `longitude` là **kinh độ** theo độ, miền hợp lệ từ -180 đến 180 nếu constructor thực thi;
- Quy ước hệ quy chiếu nếu domain phụ thuộc vào hệ tọa độ;
- Khả năng null nếu component là reference type, hoặc miền số đặc biệt như NaN/Infinity nếu liên quan.

Ví dụ bổ sung validation:

```java
/**
 * Một cặp tọa độ theo độ địa lý.
 *
 * @param latitude vĩ độ, số hữu hạn từ -90 đến 90 độ
 * @param longitude kinh độ, số hữu hạn từ -180 đến 180 độ
 */
record GeoPoint(double latitude, double longitude) {
    GeoPoint {
        if (!Double.isFinite(latitude) || latitude < -90 || latitude > 90
                || !Double.isFinite(longitude)
                || longitude < -180 || longitude > 180) {
            throw new IllegalArgumentException("Invalid coordinates");
        }
    }
}
```

**Vì sao nhắc tới NaN?** So sánh bằng `<` và `>` với NaN đều trả false. Nếu chỉ viết `latitude < -90 || latitude > 90`, NaN có thể lọt qua. Khi tài liệu hứa “số hữu hạn”, implementation phải kiểm tra `Double.isFinite`.

### Component được tách từ record lồng

```java
record Route(String id, GeoPoint start, GeoPoint finish) {}

if (value instanceof Route(
        var id,
        GeoPoint(var startLat, var startLon),
        GeoPoint(var endLat, var endLon))) {
    System.out.println(id);
}
```

Pattern yêu cầu `Route`, `start` và `finish` là các record tương ứng không-null. Nếu component `start` nullable, nested `GeoPoint(...)` không khớp khi nó null. Tài liệu của `Route.start`/`Route.finish` cần nêu rõ các invariant ấy; đừng dựa hoàn toàn vào mẫu lồng như một cơ chế thay thế cho validation.

**Nguyên tắc API:** Record pattern là nơi tiêu thụ contract đã có. Nó không sửa contract và không “bảo vệ” các component chưa được constructor kiểm tra.

## 10. Ví dụ Java 21 độc lập: record, Javadoc và pattern matching

Chương trình dưới đây thể hiện cách viết Javadoc cho:
- Record component có `@param` ngay trên khai báo record;
- Compact constructor có mô tả normalization, exception;
- Collection component được copy phòng vệ;
- Accessor tường minh có `@return`;
- Một phương thức tính toán có Javadoc riêng;
- Pattern matching cho `switch` dùng đúng thứ tự component.

Tạo file **`RecordComponentDocumentationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

/**
 * Minh họa hợp đồng API cho các record component.
 *
 * @since 1.0
 */
public class RecordComponentDocumentationDemo {

    /**
     * Mã sản phẩm đã chuẩn hóa; dùng để nhận diện một loại sản phẩm.
     *
     * @param value mã sản phẩm sau chuẩn hóa, gồm 2-20 ký tự
     *              ASCII A-Z, 0-9 hoặc dấu gạch nối; không null
     */
    public record ProductCode(String value) {

        /**
         * Chuẩn hóa và kiểm tra mã sản phẩm trước khi lưu.
         *
         * @throws NullPointerException nếu value là null
         * @throws IllegalArgumentException nếu mã sai định dạng
         */
        public ProductCode {
            value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);
            if (!value.matches("[A-Z0-9-]{2,20}")) {
                throw new IllegalArgumentException(
                    "Invalid product code");
            }
        }
    }

    /**
     * Một dòng đơn hàng có số lượng sản phẩm dương.
     *
     * @param code mã sản phẩm bắt buộc, không null
     * @param quantity số đơn vị sản phẩm, phải lớn hơn 0
     */
    public record LineItem(ProductCode code, int quantity) {

        /**
         * Kiểm tra tính hợp lệ của mã và số lượng.
         *
         * @throws NullPointerException nếu code là null
         * @throws IllegalArgumentException nếu quantity không dương
         */
        public LineItem {
            Objects.requireNonNull(code, "code");
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                    "Quantity must be positive");
            }
        }
    }

    /**
     * Ảnh chụp các dòng của một đơn hàng tại thời điểm tạo.
     *
     * @param id mã đơn hàng sau khi loại khoảng trắng hai đầu,
     *           bắt buộc không null hoặc blank
     * @param lines danh sách không null, không rỗng, không có
     *              phần tử null; được copy thành danh sách
     *              không cho sửa cấu trúc, giữ nguyên thứ tự
     */
    public record OrderSnapshot(String id, List<LineItem> lines) {

        /**
         * Chuẩn hóa id và sao chép danh sách đầu vào.
         *
         * @throws NullPointerException nếu id hoặc lines là null,
         *                              hoặc lines chứa phần tử null
         * @throws IllegalArgumentException nếu id blank hoặc
         *                                  danh sách rỗng
         */
        public OrderSnapshot {
            id = Objects.requireNonNull(id, "id").strip();
            if (id.isEmpty()) {
                throw new IllegalArgumentException("Blank order id");
            }
            lines = List.copyOf(
                Objects.requireNonNull(lines, "lines"));
            if (lines.isEmpty()) {
                throw new IllegalArgumentException("Empty lines");
            }
        }

        /**
         * Tính tổng số lượng sản phẩm trong các dòng.
         *
         * @return tổng quantity của tất cả dòng; luôn dương
         * @throws ArithmeticException nếu tổng vượt phạm vi int
         */
        public int totalUnits() {
            int total = 0;
            for (LineItem item : lines) {
                total = Math.addExact(total, item.quantity());
            }
            return total;
        }
    }

    /**
     * Tên thành phố đã được loại khoảng trắng hai đầu.
     *
     * @param name tên không null/blank sau khi chuẩn hóa
     */
    public record City(String name) {

        /**
         * Chuẩn hóa thành phố khi tạo.
         *
         * @throws NullPointerException nếu name là null
         * @throws IllegalArgumentException nếu name blank
         */
        public City {
            name = Objects.requireNonNull(name, "name").strip();
            if (name.isEmpty()) {
                throw new IllegalArgumentException("Blank city");
            }
        }

        /**
         * Trả về tên thành phố đã chuẩn hóa.
         *
         * @return tên không null, không blank
         */
        public String name() {
            return name;
        }
    }

    /**
     * Diễn giải giá trị qua record patterns Java 21.
     *
     * @param value giá trị cần phân loại, có thể null
     * @return mô tả ngắn cho kiểu dữ liệu nhận được
     */
    public static String describe(Object value) {
        return switch (value) {
            case null -> "null";

            case OrderSnapshot(var id, var lines)
                    when lines.size() > 1 ->
                id + ": " + lines.size() + " dòng";

            case OrderSnapshot(var id, var lines) ->
                id + ": 1 dòng";

            case City(var name) ->
                "Thành phố: " + name;

            default -> "khác";
        };
    }

    /**
     * Chạy các tình huống minh họa API.
     *
     * @param args tham số dòng lệnh, không sử dụng
     */
    public static void main(String[] args) {
        List<LineItem> source = new ArrayList<>();
        source.add(new LineItem(new ProductCode(" pen "), 2));

        OrderSnapshot first = new OrderSnapshot(" OD-01 ", source);
        source.add(new LineItem(new ProductCode("BOOK"), 4));

        System.out.println("Mã: "
            + first.lines().get(0).code().value());
        System.out.println("Số dòng: " + first.lines().size());
        System.out.println("Tổng món: " + first.totalUnits());
        System.out.println(describe(first));

        OrderSnapshot second = new OrderSnapshot(
            "OD-02",
            List.of(
                new LineItem(new ProductCode("pen"), 1),
                new LineItem(new ProductCode("book"), 3)));

        System.out.println(describe(second));
        System.out.println(describe(new City(" Huế ")));

        try {
            first.lines().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("Danh sách không thể sửa");
        }

        try {
            new ProductCode(" ");
        } catch (IllegalArgumentException ex) {
            System.out.println("Mã rỗng bị từ chối");
        }

        System.out.println(describe(null));
        System.out.println(describe(123));
    }
}
```

Biên dịch và chạy trong thư mục chứa file, dùng **JDK 21+**:

```bash
javac --release 21 -encoding UTF-8 RecordComponentDocumentationDemo.java
java RecordComponentDocumentationDemo
```

**Kết quả dự kiến chính xác:**

```text
Mã: PEN
Số dòng: 1
Tổng món: 2
OD-01: 1 dòng
OD-02: 2 dòng
Thành phố: Huế
Danh sách không thể sửa
Mã rỗng bị từ chối
null
khác
```

### Phân tích mối liên hệ giữa Javadoc và hành vi

1. `ProductCode(" pen ")` tạo mã `"PEN"`. `@param value` nói về định dạng lưu; compact constructor chuẩn hóa bằng `strip` và `Locale.ROOT`, sau đó kiểm tra regex.
2. `LineItem.quantity` phải dương. Điều kiện được thực thi trong constructor, không chỉ ghi ở Javadoc.
3. `OrderSnapshot.lines` là danh sách không cho sửa cấu trúc. Thêm phần tử vào `source` sau khi tạo không thay đổi `first.lines()`, nên chỉ còn một dòng và tổng món là 2.
4. `totalUnits()` dùng `Math.addExact`: nếu tổng số nguyên vượt miền `int` thì ném `ArithmeticException` đúng như tài liệu method, thay vì overflow âm thầm.
5. `City.name()` là accessor tường minh, có Javadoc `@return`, trả tên đã chuẩn hóa từ constructor.
6. `describe` dùng `OrderSnapshot(var id, var lines)`: thứ tự component trong pattern đúng với header; nhánh có guard đứng trước nhánh tổng quát cùng kiểu.
7. `case null` tường minh phân loại selector null. Không dựa vào `default` để nhận null trong pattern-matching switch.

Các đối tượng ở ví dụ chỉ mang dữ liệu minh họa, chưa là domain order đầy đủ với transaction, persistence, pricing hoặc trạng thái thanh toán.

## 11. Tạo tài liệu HTML bằng công cụ `javadoc`

Với JDK 21 đã được cài, dùng chính file Java ở mục 10:

```bash
javadoc -d api-doc -public -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -Xdoclint:all RecordComponentDocumentationDemo.java
```

Lệnh này:
- Đọc documentation comments trong source;
- Tạo HTML vào thư mục `api-doc`;
- Giữ encoding UTF-8 để các dấu tiếng Việt được xử lý đúng;
- Chỉ sinh phần API public với `-public`;
- Bật kiểm tra Javadoc bằng `-Xdoclint:all` (ví dụ thiếu tag, tham chiếu sai, HTML hoặc cú pháp Javadoc không hợp lệ).

**Cách kiểm tra thủ công sau khi chạy:**

1. Mở trang HTML của `RecordComponentDocumentationDemo`, xem nhóm nested record public.
2. Mở `ProductCode` và tìm mô tả cho component `value`; đối chiếu normalization với constructor.
3. Mở `LineItem` để kiểm tra contract `quantity > 0` và exception.
4. Mở `OrderSnapshot` để đọc mô tả `lines` về null/ownership, và `totalUnits()` về overflow.
5. Mở `City` để xem accessor `name()` với `@return`.
6. Kiểm tra cảnh báo `javadoc` thay vì chỉ dựa vào exit code của `javac`.
7. Bổ sung hoặc sửa Javadoc, sinh lại HTML để đối chiếu. Tránh sửa generated HTML bằng tay nếu source là nguồn chân lý.

`javac` kiểm tra **ngữ pháp và kiểu của mã Java**, còn `javadoc`/doclint giúp kiểm tra nhiều khía cạnh của **tài liệu API**. Không công cụ nào có thể chứng minh hoàn toàn câu “đầu vào luôn được chuẩn hóa” đúng với mọi nhánh runtime nếu không có code/test.

### `@param` sai tên và thiếu nội dung

Ví dụ record:

```java
/**
 * Một số lượng.
 *
 * @param count số lượng phần tử
 */
record Quantity(int quantity) {}
```

`@param count` không khớp tên `quantity`; một công cụ Javadoc có kiểm tra tag tham chiếu có thể báo lỗi/cảnh báo. Cách đúng:

```java
/** @param quantity số lượng phần tử */
record Quantity(int quantity) {}
```

Đừng tắt doclint toàn bộ để che vấn đề nếu mục tiêu là xuất bản tài liệu chất lượng cao.

## 12. Các tag Javadoc thường gặp và nơi dùng đúng

| Tag | Đặt ở đâu? | Ví dụ mục đích |
| --- | --- | --- |
| `@param componentName` | Javadoc của `record` | Mô tả record component |
| `@param <T>` | Javadoc của generic record | Mô tả kiểu phần tử |
| `@param parameterName` | Javadoc constructor/method | Mô tả tham số thực của constructor/method |
| `@return` | Javadoc của method/accessor | Giải thích giá trị trả về |
| `@throws` / `@exception` | Javadoc của constructor hoặc method | Trường hợp ném exception; ưu tiên `@throws` |
| `@since` | Type hoặc member liên quan | Mốc version API bắt đầu tồn tại |
| `@see` | Type/member | Liên kết tham khảo API liên quan |
| `{@link ...}` | Nội dung Javadoc phù hợp | Tham chiếu clickable đến một type/member |
| `{@code ...}` | Nội dung Javadoc | Biểu diễn code/literal mà không diễn giải HTML |
| `{@literal ...}` | Nội dung Javadoc | Biểu diễn literal không áp font code |
| `{@inheritDoc}` | Method thực sự kế thừa tài liệu hợp lệ | Không dùng mặc định cho record component |

**Phân biệt `@param` trên type và trên method:** Với record, `@param` ở khai báo record nói về các component. Trên một method, `@param` nói về tham số method. Nó không phải cách viết tag Javadoc trực tiếp cho một field ẩn bên trong record.

**Tránh `@return` trên record:** Record declaration không có return value; accessor method mới có. Nếu thêm `@return` ngay trước khai báo `record`, tag đó sai ngữ cảnh Javadoc.

**Dùng link đúng đối tượng:** Nếu muốn nói về accessor, tham chiếu `{@link #name()}` trong Javadoc của `City` có thể chỉ đến phương thức accessor; một record component trong header không phải đối tượng tham chiếu method bằng chính tên field thông thường.

## 13. Tài liệu và backward compatibility

Record mang một contract về **danh sách component**. Thay:

```java
public record Point(int x, int y) {}
```

thành:

```java
public record Point(int x, int y, int z) {}
```

không chỉ thêm một dòng Javadoc. Thay đổi này có thể ảnh hưởng:
- Lời gọi canonical constructor: `new Point(1, 2)` không còn đúng nếu không có constructor hỗ trợ riêng.
- Record patterns: `Point(var x, var y)` không còn đúng số component của record 3 chiều.
- Accessor, component descriptor và reflection.
- Equality, hashCode, `toString` mặc định vì tập component thay đổi.
- Một số schema, serialization hoặc mapper của thư viện ngoài.

**Thay đổi tài liệu phải đi cùng review API và test.** Tên, thứ tự và ý nghĩa component là một phần của thiết kế public API. Với API được dùng rộng, có thể chọn một record mới như `Point3D`, constructor tương thích có chủ đích hoặc một DTO version mới, thay vì âm thầm phá lời gọi hiện có.

Nếu **đổi nghĩa** component mà không đổi chữ ký, nguy cơ còn khó phát hiện hơn: `amount` từ “cent” thành “đồng” vẫn là `long` và `javac` không báo lỗi. Javadoc với đơn vị đo rõ ràng, tên cụ thể như `minorUnits` và test contract sẽ giảm sai sót.

## 14. Checklist review Javadoc của record component

| Câu hỏi | Kết quả mong muốn |
| --- | --- |
| Javadoc có nằm ngay trước khai báo record? | Dùng `/** ... */`, không phải `//` |
| Mỗi component có `@param` đúng tên? | Không sót, không nhầm tên sau refactor |
| Mô tả record tổng thể có nêu ý nghĩa domain? | Không lặp một câu vô nghĩa như “chứa dữ liệu” |
| Số liệu có đơn vị và miền hợp lệ? | Ví dụ `minorUnits >= 0`, đơn vị rõ |
| Reference có null contract? | Ghi rõ required, optional, ý nghĩa của null |
| Normalization có được mô tả đúng? | `strip`, uppercase, rounding nếu thật sự được làm |
| Collection có ownership và null policy? | Copy, unmodifiable, thứ tự, phần tử null |
| Deep immutability có bị hứa quá mức? | Phân biệt final reference với mutable elements |
| Constructor có thực thi invariant? | Javadoc khớp validation thực tế |
| Accessor custom có hành vi và `@return`? | Không mâu thuẫn với trạng thái được lưu |
| Exception có được tài liệu đúng chỗ? | `@throws` ở constructor/method |
| Record pattern sử dụng đúng thứ tự component? | Không đảo hai component cùng kiểu |
| Có kiểm tra `javadoc -Xdoclint:all`? | Không bỏ qua cảnh báo tham chiếu/tag |
| Đã xem HTML sinh ra? | Nội dung dễ đọc và đủ cho người dùng API |
| Thay đổi record có xét compatibility? | Constructor, patterns, equality, schema |

### Quy tắc đọc nhanh

Với một record mới, reviewer phải trả lời được trong khoảng một lượt đọc:
1. Giá trị này là gì?
2. Từng component đo/biểu diễn điều gì?
3. Đối tượng hợp lệ được tạo như thế nào?
4. Điều gì có thể null hoặc thay đổi được?
5. Có điều gì trong API phụ thuộc vào thứ tự/số lượng component?

Nếu không trả lời được, cần bổ sung **contract ở tên/type/Javadoc/constructor**, không phải chỉ viết thêm một đoạn mô tả chung.

## 15. Lỗi phổ biến

**Lỗi 1 — thiếu `@param` của component.** Record có hai, ba component nhưng chỉ có Javadoc một dòng “dữ liệu record”. Người dùng không biết đơn vị và miền giá trị. Thêm `@param` đúng tên.

**Lỗi 2 — viết `@return` ngay trên record.** Đây là tag của method, không phải type declaration. Đặt `@return` trên accessor/method khi cần.

**Lỗi 3 — mô tả non-null nhưng constructor vẫn cho null.** Javadoc không tự tạo runtime check. Dùng `Objects.requireNonNull` hoặc validation tương ứng, viết test.

**Lỗi 4 — ghi “immutable” khi chứa list mutable.** Final reference không đóng băng object con. Nêu ownership và có defensive copy nếu đó là invariant.

**Lỗi 5 — mô tả unit sai.** `amount=1000` có thể bị hiểu thành 1000 đồng thay vì 1000 cent. Đặt tên `minorUnits`/`cents` và mô tả chính xác.

**Lỗi 6 — tài liệu normalization sai hành vi.** Ghi “uppercased” nhưng constructor chỉ `strip`, hoặc ngược lại. Test input cần chuẩn hóa và cập nhật đồng bộ code/docs.

**Lỗi 7 — dùng `@param` tên cũ sau refactor.** Header đã đổi từ `value` sang `code` nhưng doc tag vẫn là `value`. Bật doclint và cập nhật ngay.

**Lỗi 8 — generic type parameter không được giải thích.** `Page<T>` có `@param items` nhưng không có `@param <T>` dù `T` có ý nghĩa domain cụ thể.

**Lỗi 9 — thêm record component mà quên API consumers.** Constructor và record patterns thay đổi, equals/hash thay đổi; review compatibility và tests.

**Lỗi 10 — custom accessor làm việc đắt/ngầm ném lỗi.** Code pattern matching có thể gọi accessor. Nếu thật sự có hành vi khác thường, cân nhắc sửa thiết kế trước; Javadoc không thay thế một API nhất quán.

**Lỗi 11 — tự sửa HTML Javadoc thay vì source.** Nội dung sinh lại sẽ mất thay đổi. Sửa source comment rồi chạy lại `javadoc`.

**Lỗi 12 — trộn Javadoc với comment TODO nội bộ.** Tài liệu công khai nên mô tả contract hiện hành, không chứa placeholder hoặc thông tin hạ tầng nhạy cảm.

## 16. Bài tập thực hành

**Bài 1 — Viết tài liệu component.** Với `record Temperature(double celsius)`, hãy ghi `@param celsius` bao gồm đơn vị °C và cách xử lý NaN/Infinity. Nếu muốn cấm các giá trị không hữu hạn, hãy bổ sung `Double.isFinite(celsius)` ở compact constructor.

**Bài 2 — Null contract.** Thiết kế `record Contact(String email, String phone)` sao cho email bắt buộc còn phone có thể null. Viết Javadoc phân biệt “vắng mặt” với “blank”, và test constructor có từ chối email null hay không.

**Bài 3 — Tạo HTML.** Chạy `javadoc -Xdoclint:all` trên `RecordComponentDocumentationDemo.java`, mở trang `OrderSnapshot` và đối chiếu mô tả `lines` với hành vi `List.copyOf`. Tìm đúng mục tài liệu cho `totalUnits()`.

**Bài 4 — Thử lỗi tag.** Đổi `@param quantity` thành `@param count` ở `LineItem` nhưng không đổi header. Chạy lại Javadoc và quan sát cảnh báo/cách phát hiện tham chiếu sai. Khôi phục tag đúng.

**Bài 5 — Record pattern.** Viết `case GeoPoint(var lat, var lon)` trên một GeoPoint đã validate. Giải thích vì sao tài liệu component vẫn cần nêu đơn vị là độ và không cho NaN.

**Bài 6 — Collection ownership.** Tạo `record Tags(List<String> values)`, dùng `List.copyOf` và ghi Javadoc cam kết list không-null, không phần tử null, không cho sửa cấu trúc. Nếu thay `String` bằng `MutableTag`, lời hứa nào phải sửa?

**Bài 7 — API evolution.** Thêm `discount` vào `LineItem`. Liệt kê các consumer bị ảnh hưởng: constructor, record pattern, equality, tài liệu và schema; đề xuất chiến lược phiên bản hóa.

**Bài 8 — Documentation vs validation.** Tìm một `@param` ghi “phải dương” nhưng constructor không kiểm tra. Viết test làm lộ giá trị âm và đưa validation vào nơi phù hợp. Kết luận vì sao Javadoc không thay thế test.

**Bài 9 — Accessor custom.** Thêm accessor tường minh `public String name()` vào một record đã chuẩn hóa. Viết `@return` phù hợp; giải thích vì sao không được tự ý trả giá trị không nhất quán với component đã lưu.

## 17. Tổng kết

**Record component là một phần của contract API, không phải chi tiết triển khai có thể bỏ qua trong tài liệu.** Khi viết Javadoc cho record:

- Đặt documentation comment **ngay trước `record`**.
- Dùng **`@param componentName`** đúng tên để mô tả từng component, và **`@param <T>`** cho type parameter của generic record.
- Ghi rõ **ý nghĩa, đơn vị, miền giá trị, nullability, normalization, ownership và bất biến** khi chúng quan trọng.
- Tài liệu hóa **`@throws`** ở constructor/method thực thi validation; dùng **`@return`** cho accessor hoặc method, không dùng `@return` trên record declaration.
- Đảm bảo lời hứa được **thực thi** bằng constructor, defensive copy và tests; Javadoc không tự áp đặt invariant.
- Đọc các record patterns như consumers của thứ tự và kiểu component.
- Chạy **`javadoc -Xdoclint:all`**, xem HTML và review backward compatibility mỗi khi thay đổi header.

### Nguồn tham khảo

- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html).
- [Oracle Java 21 — Documentation Comment Specification for the Standard Doclet](https://docs.oracle.com/en/java/javase/21/docs/specs/javadoc/doc-comment-spec.html).
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Java SE 21 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Record.html).
- [JEP 395 — Records](https://openjdk.org/jeps/395).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
