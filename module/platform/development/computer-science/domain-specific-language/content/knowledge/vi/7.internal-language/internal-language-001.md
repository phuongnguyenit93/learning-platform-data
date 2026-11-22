# API thông thạo (fluent API)

## 1. Khái niệm và vai trò trong DSL nội bộ

**API thông thạo (*fluent API*)** là phong cách thiết kế giao diện lập trình cho phép người dùng nối tiếp nhiều lời gọi phương thức thành một biểu thức có trình tự rõ ràng. Mỗi phương thức thường trả về chính đối tượng hiện tại hoặc một đối tượng tiếp theo có liên quan, để lời gọi sau tiếp tục trên kết quả đó.

Ví dụ:

```java
String result = Stream.of("An", "Binh", "Chi")
    .filter(name -> name.length() > 2)
    .map(String::toUpperCase)
    .sorted()
    .findFirst()
    .orElse("UNKNOWN");
```

Đoạn mã thể hiện một chuỗi thao tác: tạo stream, lọc, chuyển đổi, sắp xếp rồi lấy kết quả. Các phương thức được đặt tên theo hành động nên người đọc có thể theo dõi ý định của chương trình từ trái sang phải.

Trong kiến trúc **DSL nội bộ (*internal DSL*)**, fluent API là một kỹ thuật quan trọng để làm cho mã nguồn trông giống một ngôn ngữ nhỏ dành cho miền nghiệp vụ. Thay vì viết một cấu hình dài bằng nhiều lời gọi hàm rời rạc, người dùng có thể ghép các thao tác theo trật tự tự nhiên của bài toán.

Ví dụ một API giả định để mô tả báo cáo:

```java
Report report = ReportBuilder.create()
    .title("Doanh thu quý")
    .section("Tổng quan", "Doanh thu tăng 12%")
    .includeChart("monthly-revenue")
    .build();
```

Các lời gọi trên vẫn là mã Java hợp lệ. Java xử lý cú pháp lời gọi phương thức; thư viện định nghĩa ý nghĩa của `title`, `section`, `includeChart` và `build`. Đây là đặc trưng của DSL nội bộ: ngôn ngữ chủ cung cấp cú pháp, còn API cung cấp từ vựng và ngữ nghĩa chuyên biệt.

## 2. Thành phần cốt lõi của fluent API

### 2.1. Method chaining

*Method chaining* (nối chuỗi phương thức) là cơ chế thường dùng để triển khai fluent API. Một phương thức trả về một đối tượng cho phép gọi phương thức tiếp theo ngay trên kết quả đó.

Ví dụ với `StringBuilder` trong Java:

```java
String message = new StringBuilder()
    .append("Hello")
    .append(", ")
    .append("DSL")
    .append("!")
    .toString();
```

`append` trả về cùng một `StringBuilder`, vì vậy các lời gọi có thể nối tiếp nhau. `toString` là thao tác kết thúc chuỗi và trả về `String`, không còn trả về builder.

Cơ chế chaining đơn giản có dạng:

```java
public class MessageBuilder {
    private final StringBuilder value = new StringBuilder();

    public MessageBuilder text(String part) {
        value.append(part);
        return this;
    }

    public String build() {
        return value.toString();
    }
}
```

Cách sử dụng:

```java
String message = new MessageBuilder()
    .text("Fluent")
    .text(" API")
    .text(" example")
    .build();
```

`return this` giữ cho chuỗi thao tác tiếp tục trên cùng một đối tượng. Đây là cách làm phổ biến khi builder có trạng thái thay đổi được.

### 2.2. Tên phương thức diễn đạt ngôn ngữ miền

Fluent API có giá trị khi tên phương thức mô tả khái niệm hoặc hành động của miền nghiệp vụ. Một chuỗi lời gọi không tự động trở thành API thông thạo chỉ vì nó có nhiều dấu chấm.

So sánh hai cách biểu đạt giả định:

```java
// API thiên về chi tiết kỹ thuật
rule.setField("customer.tier");
rule.setOperator("EQUALS");
rule.setValue("GOLD");
rule.setAction("SET_DISCOUNT");
rule.setAmount(10);
```

```java
// API diễn đạt khái niệm của miền
rule.whenCustomerTierIs("GOLD")
    .applyDiscountPercent(10);
```

Cách thứ hai làm rõ ý định nghiệp vụ hơn. Người thiết kế cần chọn từ vựng mà người dùng DSL hiểu, thống nhất cách đặt tên và tránh trộn lẫn thuật ngữ kỹ thuật với thuật ngữ miền khi không cần thiết.

### 2.3. Đối tượng trả về

Phương thức trong một fluent API có thể trả về:

- **`this`:** tiếp tục thao tác trên cùng một đối tượng có trạng thái thay đổi được.
- **Một builder mới:** tạo trạng thái mới và giữ đối tượng cũ không đổi, thường dùng cho thiết kế bất biến.
- **Một kiểu chuyên biệt khác:** chuyển sang giai đoạn tiếp theo của quy trình hoặc mở ra một nhóm thao tác khác.
- **Kết quả cuối cùng:** kết thúc chuỗi, chẳng hạn `build()`, `execute()`, `send()` hoặc `toList()`.

Việc chọn kiểu trả về quyết định người dùng có thể gọi thao tác nào tiếp theo. Vì vậy, chữ ký phương thức là một phần của thiết kế ngôn ngữ, không chỉ là chi tiết triển khai.

## 3. Fluent API và các khái niệm liên quan

Các thuật ngữ dưới đây thường xuất hiện cùng nhau nhưng không đồng nghĩa.

| Khái niệm | Ý nghĩa | Quan hệ với fluent API |
|---|---|---|
| Method chaining | Nối nhiều lời gọi phương thức thông qua giá trị trả về | Cơ chế kỹ thuật thường dùng |
| Fluent interface / fluent API | Thiết kế API để chuỗi lời gọi dễ đọc và diễn đạt ý định | Phong cách thiết kế |
| Builder pattern | Tạo đối tượng phức tạp qua các bước cấu hình rồi hoàn tất | Thường dùng fluent API để cấu hình builder |
| Internal DSL | Ngôn ngữ chuyên biệt được nhúng trong cú pháp của ngôn ngữ chủ | Có thể dùng fluent API làm cú pháp biểu đạt |
| Lambda / closure DSL | Dùng khối hàm để gom các thao tác hoặc biểu thức miền | Có thể kết hợp với fluent API |

Ví dụ, `StringBuilder.append(...).append(...)` có method chaining và API thông thạo, nhưng không nhất thiết là một DSL miền hoàn chỉnh. Một builder tạo truy vấn hoặc workflow với từ vựng chuyên biệt có thể trở thành một phần của internal DSL.

Builder pattern tập trung vào quá trình tạo một đối tượng. Fluent API rộng hơn: nó có thể dùng để xây dựng cấu hình, truy vấn, pipeline, giao dịch, kịch bản kiểm thử hoặc chuỗi hành động. Một builder có thể không fluent; một fluent API cũng không nhất thiết là builder.

## 4. Các kiểu thiết kế fluent API

### 4.1. API thay đổi trạng thái và trả về `this`

Đây là cách đơn giản nhất. Mỗi phương thức thay đổi trạng thái nội bộ rồi trả về cùng đối tượng.

```java
public final class ReportBuilder {
    private String title;
    private final List<String> sections = new ArrayList<>();
    private boolean includeSummary;

    public ReportBuilder title(String title) {
        this.title = Objects.requireNonNull(title);
        return this;
    }

    public ReportBuilder section(String heading, String body) {
        sections.add(heading + ": " + body);
        return this;
    }

    public ReportBuilder includeSummary() {
        includeSummary = true;
        return this;
    }

    public Report build() {
        if (title == null || title.isBlank()) {
            throw new IllegalStateException("Report title is required");
        }

        return new Report(title, List.copyOf(sections), includeSummary);
    }
}
```

Một kiểu `Report` bất biến có thể được định nghĩa bằng record:

```java
public record Report(
    String title,
    List<String> sections,
    boolean includeSummary
) {}
```

Cách sử dụng:

```java
Report report = new ReportBuilder()
    .title("Doanh thu quý")
    .section("Tổng quan", "Doanh thu tăng 12%")
    .section("Chi phí", "Chi phí vận hành ổn định")
    .includeSummary()
    .build();
```

Ưu điểm là dễ hiểu và dễ triển khai. Tuy nhiên, builder có trạng thái nên cần chú ý vòng đời đối tượng. Không nên chia sẻ một builder đang được cấu hình giữa nhiều luồng nếu chưa thiết kế đồng bộ. Sau `build()`, nhóm cần quyết định builder có được phép tiếp tục thay đổi và tạo kết quả mới hay không.

### 4.2. API bất biến

Với API bất biến, mỗi thao tác trả về một đối tượng mới chứa cấu hình đã cập nhật. Đối tượng ban đầu không bị thay đổi.

```java
public record QueryOptions(
    String table,
    String condition,
    int limit
) {
    public QueryOptions where(String condition) {
        return new QueryOptions(table, condition, limit);
    }

    public QueryOptions limit(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException("Limit must be positive");
        }
        return new QueryOptions(table, condition, value);
    }
}
```

Ví dụ trên chỉ minh họa ý tưởng; trong một API hoàn chỉnh, phương thức khởi tạo hoặc factory sẽ cung cấp giá trị `table` ban đầu và các phương thức cập nhật cần giữ nguyên mọi trường cấu hình khác.

API bất biến có các lợi ích:

- Dễ suy luận vì lời gọi không sửa đối tượng cũ.
- Ít rủi ro khi chia sẻ giữa nhiều luồng nếu toàn bộ trạng thái thành phần cũng bất biến.
- Có thể lưu lại nhiều cấu hình trung gian để so sánh hoặc tái sử dụng.
- Phù hợp với biểu thức hàm và pipeline.

Đổi lại, việc tạo nhiều đối tượng có thể tăng chi phí cấp phát, dù JVM thường tối ưu được nhiều trường hợp. Cần đo hiệu năng thay vì mặc định rằng bất biến luôn chậm.

### 4.3. Chuyển trạng thái bằng kiểu trả về

Một fluent API có thể trả về các kiểu khác nhau để thể hiện giai đoạn hiện tại. Cách này giúp ngăn một số thao tác không hợp lệ ngay khi biên dịch.

Ví dụ, một API tạo yêu cầu chỉ cho phép gửi sau khi đã đặt địa chỉ:

```java
public interface RequestStart {
    RequestWithAddress to(URI address);
}

public interface RequestWithAddress {
    RequestWithAddress header(String name, String value);
    RequestReady timeout(Duration duration);
}

public interface RequestReady {
    RequestReady header(String name, String value);
    HttpRequest send();
}
```

Đây là phác thảo về *staged builder*. Trong triển khai thực tế, các interface cần được hỗ trợ bởi implementation và factory khởi tạo. Kiểu trả về giới hạn tập phương thức có thể gọi ở mỗi giai đoạn. Người dùng không thể gọi `send()` trước khi có một đối tượng `RequestReady`.

Thiết kế theo giai đoạn hữu ích khi thứ tự thao tác là yêu cầu cứng của miền, chẳng hạn phải chọn tài khoản trước khi chuyển tiền hoặc phải khai báo nguồn trước khi tạo pipeline. Không nên áp dụng cho mọi API vì quá nhiều kiểu trung gian có thể làm thư viện khó học và khó bảo trì.

### 4.4. Fluent API kết hợp lambda

Một số ngôn ngữ hỗ trợ lambda, closure hoặc block syntax có thể tạo ra DSL nội bộ tự nhiên hơn. Fluent API mở đầu một cấu trúc, còn lambda gom nhóm các thao tác bên trong.

Ví dụ Kotlin minh họa:

```kotlin
workflow("nightly") {
    schedule("02:00")
    task("backup") {
        runCommand("backup-data")
        notify("operations")
    }
}
```

Cú pháp block trong Kotlin được triển khai bằng lambda với receiver hoặc tham số hàm tùy API. Nó vẫn tuân theo cú pháp Kotlin, trong khi thư viện định nghĩa ý nghĩa của `workflow`, `schedule`, `task`, `runCommand` và `notify`.

Kết hợp fluent API với lambda thường phù hợp với cấu trúc phân cấp như workflow, form, route, test specification và cấu hình build.

## 5. Ví dụ xây dựng một fluent API cho truy vấn

Giả sử cần một API nội bộ để mô tả truy vấn đối tượng `Person`. Mục tiêu là cho phép người dùng đọc được các thao tác theo thứ tự: chọn nguồn, lọc, sắp xếp và giới hạn kết quả.

### 5.1. Cách sử dụng mong muốn

```java
Query<Person> query = Query.from(Person.class)
    .where(person -> person.age() >= 18)
    .orderBy(Comparator.comparing(Person::lastName))
    .limit(20);
```

Đây là ví dụ API giả định. `Query.from` tạo truy vấn; các phương thức trả về cấu hình truy vấn để nối tiếp; `where` nhận predicate; `orderBy` nhận comparator; `limit` đặt giới hạn.

### 5.2. Thiết kế kiểu dữ liệu miền

```java
public record Person(
    String firstName,
    String lastName,
    int age
) {}
```

### 5.3. Một implementation bất biến giản lược

```java
public final class Query<T> {
    private final Class<T> type;
    private final List<Predicate<T>> filters;
    private final Comparator<T> comparator;
    private final int maxResults;

    private Query(
        Class<T> type,
        List<Predicate<T>> filters,
        Comparator<T> comparator,
        int maxResults
    ) {
        this.type = type;
        this.filters = List.copyOf(filters);
        this.comparator = comparator;
        this.maxResults = maxResults;
    }

    public static <T> Query<T> from(Class<T> type) {
        return new Query<>(type, List.of(), null, Integer.MAX_VALUE);
    }

    public Query<T> where(Predicate<T> condition) {
        List<Predicate<T>> next = new ArrayList<>(filters);
        next.add(Objects.requireNonNull(condition));

        return new Query<>(type, next, comparator, maxResults);
    }

    public Query<T> orderBy(Comparator<T> comparator) {
        return new Query<>(
            type, filters, Objects.requireNonNull(comparator), maxResults
        );
    }

    public Query<T> limit(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException("Limit must be positive");
        }

        return new Query<>(type, filters, comparator, value);
    }

    public List<T> execute(Collection<T> source) {
        Stream<T> stream = source.stream();

        for (Predicate<T> filter : filters) {
            stream = stream.filter(filter);
        }

        if (comparator != null) {
            stream = stream.sorted(comparator);
        }

        return stream.limit(maxResults).toList();
    }
}
```

Implementation này minh họa các quyết định thiết kế quan trọng:

- Các trường cấu hình là `final`.
- Danh sách predicate được sao chép khi tạo đối tượng.
- Mỗi thao tác trả về một `Query` mới.
- `execute` là thao tác kết thúc, trả về dữ liệu thay vì tiếp tục chuỗi truy vấn.
- `limit` kiểm tra dữ liệu đầu vào ngay tại ranh giới API.

Các import cần thiết trong một tệp Java gồm `ArrayList`, `Collection`, `Comparator`, `List`, `Objects`, `Predicate` và `Stream` từ các package tương ứng của Java. Một triển khai sản phẩm có thể cần thêm kiểm tra kiểu nguồn, hỗ trợ nhiều thứ tự sắp xếp, xử lý null, phân trang, projection và tối ưu thực thi.

### 5.4. Sử dụng API

```java
List<Person> adults = Query.from(Person.class)
    .where(person -> person.age() >= 18)
    .where(person -> person.lastName() != null)
    .orderBy(Comparator.comparing(Person::lastName))
    .limit(20)
    .execute(people);
```

Người dùng tập trung vào điều kiện truy vấn và không cần biết danh sách predicate được lưu hoặc stream được tạo như thế nào. Đây là mục tiêu của một fluent API tốt: che giấu chi tiết kỹ thuật, giữ cho biểu thức thể hiện ý định miền.

## 6. Thiết kế thứ tự và ngữ nghĩa của chuỗi lời gọi

### 6.1. Thứ tự có ý nghĩa hay không?

Một fluent API có thể cho phép các thao tác theo bất kỳ thứ tự nào hoặc yêu cầu một trình tự nhất định.

Ví dụ, `where(...).limit(10)` và `limit(10).where(...)` có thể mang cùng ý nghĩa nếu cả hai chỉ cấu hình một truy vấn rồi thực thi sau. Nhưng với API thao tác trực tiếp trên dữ liệu, thứ tự có thể làm thay đổi kết quả.

Nhóm thiết kế phải quyết định:

- Phương thức chỉ ghi nhận cấu hình hay thực hiện hành động ngay?
- Hai thao tác có giao hoán được không?
- Có cho phép gọi một phương thức nhiều lần không?
- Gọi lại phương thức sẽ thay thế cấu hình trước hay bổ sung cấu hình?
- Có thao tác nào kết thúc chuỗi hoặc làm đối tượng không còn sử dụng được không?

Các quy tắc này cần thể hiện nhất quán trong tên phương thức, kiểu trả về và tài liệu.

### 6.2. Phương thức cấu hình và phương thức kết thúc

Một fluent API thường có hai nhóm phương thức:

| Nhóm | Ví dụ | Vai trò |
|---|---|---|
| Intermediate/configuration | `where`, `header`, `timeout`, `section` | Cấu hình hoặc xây dựng thêm biểu thức |
| Terminal | `build`, `execute`, `send`, `toList` | Tạo kết quả hoặc thực thi chuỗi thao tác |

Tên gọi không phải quy tắc bắt buộc, nhưng phân biệt hai nhóm giúp người dùng biết khi nào chuỗi kết thúc. Phương thức terminal có thể trả về kết quả nghiệp vụ, một đối tượng đã hoàn chỉnh hoặc một kiểu bất đồng bộ như `CompletableFuture<T>`.

### 6.3. Tác dụng phụ và thời điểm thực thi

Có hai kiểu hành vi phổ biến:

- **Khai báo trì hoãn (*declarative/lazy*):** lời gọi chỉ xây dựng mô tả công việc. Hành động xảy ra khi gọi terminal method.
- **Thực thi tức thời (*eager/imperative*):** mỗi lời gọi thực hiện ngay một phần công việc và trả về đối tượng để tiếp tục.

Ví dụ Java Stream dùng các intermediate operations như `filter` và `map` để xây dựng pipeline; việc xử lý thường chỉ bắt đầu khi có terminal operation như `toList` hoặc `count`. Trong khi đó, `StringBuilder.append` thay đổi nội dung ngay khi được gọi.

Tài liệu API cần nói rõ thời điểm thực thi, bởi nó ảnh hưởng đến hiệu năng, lỗi, transaction, logging và việc sử dụng lại đối tượng.

## 7. Quy tắc thiết kế fluent API dễ hiểu và an toàn

### 7.1. Dùng từ vựng nhất quán

Tên phương thức nên phản ánh thuật ngữ miền. Nếu API sử dụng `customer`, `order` và `discount`, hãy tránh đổi sang các tên kỹ thuật như `entity1`, `node` hoặc `payload` ở những phần tương đương mà không có lý do.

Một phương thức nên biểu đạt một hành động rõ ràng. Tránh tên quá chung như `set`, `do`, `process` nếu có thể dùng `applyDiscount`, `scheduleAt` hoặc `assignOwner`.

### 7.2. Giữ chuỗi lời gọi có thể đọc được

Không nên ép mọi thứ vào một dòng. Xuống dòng theo từng thao tác giúp người đọc xem xét, review và debug dễ hơn.

```java
Report report = ReportBuilder.create()
    .title("Monthly operations")
    .section("Availability", "99.95%")
    .section("Incidents", "2")
    .includeSummary()
    .build();
```

Một chuỗi quá dài có thể là dấu hiệu API đang gánh nhiều trách nhiệm. Có thể tách thành biến trung gian, phương thức trợ giúp hoặc các cấu hình con có tên rõ ràng.

### 7.3. Xác thực đầu vào tại đúng thời điểm

Nếu giá trị không hợp lệ có thể phát hiện ngay, API nên báo lỗi tại phương thức nhận giá trị đó thay vì đợi đến lúc thực thi.

Ví dụ, `limit(0)` có thể bị từ chối ngay. Tuy nhiên, một số quy tắc chỉ có thể kiểm tra khi đã có đầy đủ context; khi đó cần chỉ rõ lỗi xảy ra ở `build`, `validate` hay `execute`.

### 7.4. Chọn mutable hay immutable có chủ đích

| Tiêu chí | Mutable fluent API | Immutable fluent API |
|---|---|---|
| Cách cập nhật | Sửa trạng thái rồi trả `this` | Tạo đối tượng mới |
| Bộ nhớ | Có thể ít cấp phát hơn | Có thể tạo nhiều đối tượng trung gian |
| Chia sẻ giữa luồng | Cần kiểm soát đồng bộ và vòng đời | Dễ chia sẻ hơn nếu toàn bộ trạng thái bất biến |
| Sử dụng lại cấu hình cũ | Khó nếu đối tượng đã bị thay đổi | Thuận tiện vì bản cũ còn nguyên |
| Triển khai | Đơn giản cho builder phổ biến | Cần sao chép trạng thái hoặc cấu trúc persistent |
| Phù hợp | Cấu hình ngắn hạn, chỉ một nơi sở hữu | Giá trị cấu hình dùng chung, biểu thức hàm, truy vấn |

Không có lựa chọn đúng cho mọi trường hợp. Hãy quyết định dựa trên vòng đời, khả năng chia sẻ và chi phí thực tế.

### 7.5. Giới hạn trạng thái không hợp lệ

Nếu một đối tượng cần có nhiều trường bắt buộc trước khi sử dụng, hãy kiểm tra tại `build()` hoặc biểu diễn giai đoạn bằng kiểu trả về. Không để một đối tượng cấu hình thiếu dữ liệu đi vào runtime rồi gây lỗi khó hiểu.

### 7.6. Xác định hành vi khi gọi lặp

Ví dụ, hai lần gọi `limit(10).limit(20)` có thể có nghĩa giới hạn cuối cùng là 20, hoặc giới hạn kết hợp là nhỏ hơn trong hai giá trị. Cả hai cách đều có thể hợp lý trong những miền khác nhau; API cần quy định rõ.

Tương tự, `header("Accept", "a").header("Accept", "b")` có thể thay thế, bổ sung hoặc từ chối header trùng. Không nên để hành vi này phụ thuộc ngẫu nhiên vào implementation.

### 7.7. Tránh lạm dụng nạp chồng phương thức

Overload có thể làm API tiện dụng nhưng quá nhiều biến thể dễ gây mơ hồ, đặc biệt với `null`, lambda và kiểu generic. Chỉ cung cấp các overload có ý nghĩa rõ ràng; dùng kiểu chuyên biệt hoặc tên phương thức khác nhau khi hành vi khác biệt đáng kể.

## 8. Fluent API trong các hệ sinh thái lập trình

### 8.1. Java

Java có nhiều API sử dụng phong cách fluent:

- `StringBuilder.append(...)` nối nội dung.
- Java Stream nối các thao tác xử lý dữ liệu.
- `HttpRequest.newBuilder(...)` cấu hình HTTP request.
- Một số thư viện kiểm thử và mocking cung cấp chuỗi lời gọi để mô tả kỳ vọng.

Ví dụ với HTTP request trong Java:

```java
HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("https://example.com/api/items"))
    .timeout(Duration.ofSeconds(5))
    .header("Accept", "application/json")
    .GET()
    .build();
```

Builder gom các tùy chọn và `build()` tạo ra request hoàn chỉnh.

### 8.2. Kotlin

Kotlin hỗ trợ lambda with receiver và extension functions, giúp xây dựng DSL nội bộ có cú pháp gọn. Một cấu hình có thể được viết bằng block thay vì nối tất cả phương thức trên một dòng.

```kotlin
val config = server {
    port = 8080
    routing {
        get("/health") {
            respond("OK")
        }
    }
}
```

Đây là cú pháp minh họa theo phong cách Kotlin DSL. Các hàm `server`, `routing`, `get` và `respond` phải được thư viện định nghĩa.

### 8.3. JavaScript và TypeScript

JavaScript/TypeScript thường sử dụng chaining cho builder, query, test và promise. Ví dụ:

```typescript
const result = await fetch("/api/users")
  .then(response => response.json())
  .then(users => users.filter(user => user.active))
  .then(activeUsers => activeUsers.length);
```

Chuỗi Promise thể hiện các bước xử lý bất đồng bộ. TypeScript còn có thể dùng generic và type inference để giữ kiểu dữ liệu qua từng bước.

### 8.4. Ruby và các ngôn ngữ có cú pháp biểu đạt cao

Một số ngôn ngữ cho phép DSL nội bộ trông gần với ngôn ngữ tự nhiên nhờ block, closure, keyword argument hoặc cú pháp linh hoạt. Tuy nhiên, fluent API vẫn phải tuân theo quy tắc parser và ngữ nghĩa của ngôn ngữ chủ.

## 9. Lợi ích và hạn chế

### 9.1. Lợi ích

- **Dễ đọc ý định:** tên phương thức và thứ tự thao tác có thể mô tả quy trình nghiệp vụ.
- **Giảm mã trung gian:** người dùng không cần tạo và cấu hình nhiều biến tạm cho từng bước.
- **Hỗ trợ tự động hoàn thành:** IDE có thể gợi ý thao tác tiếp theo dựa trên kiểu trả về.
- **Tăng tính nhất quán:** API giới hạn cách biểu đạt, tránh mỗi nơi tự xây dựng cấu hình khác nhau.
- **Có thể kiểm tra ở thời điểm biên dịch:** generic, overload và kiểu trả về giúp phát hiện một số cách sử dụng không hợp lệ.
- **Phù hợp với internal DSL:** có thể tạo cú pháp chuyên biệt mà không phải xây parser riêng.

### 9.2. Hạn chế

- **Bị giới hạn bởi cú pháp ngôn ngữ chủ:** fluent API không thể tự tạo từ khóa hay grammar hoàn toàn mới.
- **Chuỗi dài khó đọc:** nhiều phương thức liên tiếp có thể che khuất logic hoặc khiến lỗi khó xác định.
- **Kiểu trả về phức tạp:** staged builder, generic lồng nhau hoặc overload quá nhiều làm API khó học.
- **Tác dụng phụ khó nhận biết:** người dùng có thể không biết lời gọi chỉ cấu hình hay đã thực hiện hành động.
- **Trạng thái mutable dễ gây lỗi:** dùng chung builder, gọi sai thứ tự hoặc tái sử dụng sau khi build có thể dẫn đến kết quả không mong muốn.
- **Chi phí thiết kế và bảo trì:** API công khai cần giữ tính nhất quán, tương thích ngược và tài liệu đầy đủ.
- **Không thay thế kiểm tra miền:** một chuỗi lời gọi đọc tốt vẫn có thể tạo ra cấu hình không hợp lệ nếu thiếu validation.

## 10. Fluent API và khả năng kiểm thử

Fluent API nên được kiểm thử ở cả mức hành vi và trải nghiệm sử dụng.

### 10.1. Kiểm thử kết quả nghiệp vụ

Kiểm tra chuỗi lời gọi tạo ra cấu hình hoặc kết quả đúng:

```java
@Test
void queryFiltersAdultsAndLimitsResults() {
    List<Person> people = List.of(
        new Person("An", "Nguyen", 17),
        new Person("Binh", "Tran", 25),
        new Person("Chi", "Le", 30)
    );

    List<Person> result = Query.from(Person.class)
        .where(person -> person.age() >= 18)
        .orderBy(Comparator.comparing(Person::lastName))
        .limit(1)
        .execute(people);

    assertEquals(1, result.size());
    assertEquals("Le", result.get(0).lastName());
}
```

### 10.2. Kiểm thử đầu vào không hợp lệ

Kiểm tra các giới hạn và trạng thái:

```java
@Test
void limitMustBePositive() {
    assertThrows(
        IllegalArgumentException.class,
        () -> Query.from(Person.class).limit(0)
    );
}
```

### 10.3. Kiểm thử bất biến

Với API bất biến, cần xác nhận thao tác mới không làm thay đổi cấu hình cũ. Với API mutable, cần xác nhận builder không bị dùng sai sau khi hoàn tất hoặc khi chia sẻ.

### 10.4. Kiểm thử khả năng sử dụng

Ví dụ trong tài liệu nên được biên dịch hoặc chạy trong test. Điều này giúp phát hiện API thay đổi nhưng README hoặc tutorial chưa cập nhật. Có thể dùng compile-time tests để xác nhận các chuỗi hợp lệ biên dịch và các trạng thái không hợp lệ bị từ chối khi thiết kế staged builder.

## 11. Các lỗi thiết kế thường gặp

1. **Trả về sai đối tượng:** phương thức cấu hình trả `void` hoặc trả kiểu không cho phép thao tác tiếp theo, làm chuỗi bị đứt.
2. **Tên phương thức thiếu ngữ nghĩa:** API có chaining nhưng người dùng vẫn phải đọc implementation mới hiểu ý nghĩa.
3. **Trộn cấu hình và thực thi:** một phương thức có tên như `withHeader` bất ngờ gửi request ngay lập tức.
4. **Không quy định thứ tự:** các lời gọi phụ thuộc thứ tự nhưng API không thể hiện hoặc không kiểm tra.
5. **Cho phép build nhiều lần không rõ hành vi:** builder có thể bị sửa sau khi tạo kết quả, khiến người dùng không biết kết quả có thay đổi hay không.
6. **Không xác thực đầu vào:** giá trị sai chỉ gây lỗi sâu bên trong runtime.
7. **Tạo quá nhiều kiểu trung gian:** API trở nên khó đọc và thông báo lỗi kiểu khó hiểu.
8. **Dùng fluent API cho mọi cấu trúc:** một số thao tác có điều kiện hoặc nhánh phức tạp dễ biểu đạt hơn bằng câu lệnh thông thường.
9. **Bỏ qua tài liệu và ví dụ:** người dùng không biết chuỗi gọi nào hợp lệ, phương thức nào kết thúc và trạng thái có thể tái sử dụng hay không.

## 12. Khi nào nên dùng fluent API?

Fluent API phù hợp khi các thao tác tạo thành một chuỗi có thứ tự, tên phương thức phản ánh rõ ý định và kiểu trả về có thể hướng người dùng đến bước tiếp theo.

Nên cân nhắc sử dụng khi:

- Xây dựng internal DSL cho truy vấn, cấu hình, workflow, quy tắc nghiệp vụ hoặc test.
- Có nhiều bước tùy chọn nhưng một trình tự cấu hình dễ hiểu.
- Muốn tận dụng type checking và IDE của ngôn ngữ chủ.
- Người dùng chủ yếu là lập trình viên hoặc người có kiến thức về ngôn ngữ chủ.
- Các thao tác có thể được biểu diễn thành những phương thức ngắn, nhất quán.

Cần cân nhắc cách biểu đạt khác khi:

- Bài toán có nhiều nhánh điều kiện hoặc vòng lặp phức tạp.
- Chuỗi lời gọi sẽ quá dài và khó theo dõi.
- Thứ tự thao tác không rõ hoặc có nhiều tác dụng phụ.
- Người dùng cần một ngôn ngữ có cú pháp độc lập với ngôn ngữ chủ.
- Cấu hình cần được lưu và chỉnh sửa bởi người không lập trình; khi đó DSL bên ngoài hoặc định dạng khai báo có thể phù hợp hơn.

Fluent API có thể kết hợp với builder, lambda và kiểu dữ liệu miền. Việc chọn kỹ thuật cần dựa trên cách người dùng suy nghĩ về nghiệp vụ và khả năng kiểm soát trạng thái của API.

## 13. Quy trình thiết kế một fluent API

Có thể đi theo quy trình sau:

1. **Xác định người dùng:** ai sẽ gọi API, họ hiểu thuật ngữ nào và cần hoàn thành công việc gì?
2. **Mô hình hóa miền:** xác định danh từ, hành động, điều kiện, trạng thái và giới hạn nghiệp vụ.
3. **Viết ví dụ sử dụng trước:** phác thảo chuỗi lời gọi mong muốn trước khi triển khai class và method.
4. **Xác định giai đoạn:** phân biệt thao tác cấu hình, thao tác chuyển trạng thái và thao tác kết thúc.
5. **Chọn mô hình trạng thái:** mutable hay immutable; trả `this`, đối tượng mới hay kiểu chuyên biệt.
6. **Thiết kế kiểm tra:** quyết định lỗi nào phát hiện ngay, lỗi nào cần đến `build`, `validate` hoặc `execute`.
7. **Xác định quy tắc gọi lặp và thứ tự:** ghi rõ hành vi khi một phương thức được gọi nhiều lần hoặc gọi sai trình tự.
8. **Tích hợp IDE:** tận dụng type inference, completion, documentation và diagnostics của ngôn ngữ chủ.
9. **Viết test và ví dụ:** kiểm tra kết quả, lỗi, trạng thái và khả năng biên dịch của cách sử dụng.
10. **Đánh giá với người dùng:** dùng thử trên tình huống nghiệp vụ thực tế, rồi điều chỉnh tên và cấu trúc API.

Một API tốt không cần có chuỗi dài. Mục tiêu là giảm khoảng cách giữa ý định nghiệp vụ và mã nguồn, đồng thời giữ cho hành vi có thể dự đoán.

## 14. Kết luận

Fluent API là phong cách thiết kế API dùng các lời gọi phương thức nối tiếp để diễn đạt một chuỗi thao tác rõ ràng. Method chaining là cơ chế triển khai phổ biến; builder pattern, lambda và kiểu trả về theo giai đoạn có thể mở rộng cách biểu đạt đó.

Trong DSL nội bộ, fluent API giúp tạo từ vựng gần với miền nghiệp vụ mà vẫn tận dụng parser, type system, IDE và công cụ của ngôn ngữ chủ. Để API thực sự hữu ích, cần chọn tên phương thức rõ nghĩa, quy định thứ tự và thời điểm thực thi, kiểm soát trạng thái, xác thực đầu vào và cung cấp test cùng tài liệu. Khi được thiết kế có chủ đích, fluent API làm cho mã nguồn dễ đọc, dễ khám phá và dễ sử dụng mà không phải xây dựng một ngôn ngữ bên ngoài hoàn chỉnh.

