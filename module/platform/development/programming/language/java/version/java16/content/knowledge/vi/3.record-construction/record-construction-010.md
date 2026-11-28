# Factory method có tên cho các cách tạo record có ý nghĩa nghiệp vụ

> **Chương:** Khởi tạo record  
> **Học phần:** `JAVA_VERSION_JAVA16` — khám phá các cải tiến từ Java 16 vẫn hữu ích trong Java hiện đại, đặc biệt là `record`. Bài này hướng dẫn dùng static factory method có tên để diễn đạt ý nghĩa nghiệp vụ của từng cách tạo record, tổ chức xác thực và chuyển đổi dữ liệu nhất quán.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích static factory method là gì và phân biệt nó với constructor.
- Nhận biết khi nào tên constructor chưa diễn đạt rõ ý nghĩa nghiệp vụ.
- Thiết kế các factory như `of`, `from`, `parse`, `copyOf` hoặc tên miền nghiệp vụ.
- Đưa xác thực chung vào canonical constructor và để factory xử lý chuyển đổi đầu vào đặc thù.
- Chọn overload hay factory method dựa trên độ rõ nghĩa của API.
- Hiểu giới hạn của factory method đối với `public record` và lựa chọn kiểu dữ liệu phù hợp.
- Kiểm thử kết quả, lỗi đầu vào và hợp đồng của từng factory.

## 1. Static factory method là gì?

Một **static factory method** là phương thức tĩnh trả về một đối tượng của kiểu đang xét hoặc một kiểu tương thích. Trong record, phương thức này thường được khai báo ngay trong thân record và gọi canonical constructor để tạo đối tượng.

Ví dụ:

```java
import java.util.Objects;

public record UserId(String value) {

    public UserId {
        value = Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException("value is required");
        }
    }

    public static UserId of(String value) {
        return new UserId(value);
    }
}
```

Cách sử dụng:

```java
UserId id = UserId.of(" U-100 ");

System.out.println(id.value()); // U-100
```

`UserId.of(...)` là static factory method. Nó không phải constructor vì:

- Có modifier `static`.
- Có tên riêng là `of`, không phải tên record `UserId`.
- Có kiểu trả về `UserId`.
- Tạo đối tượng bằng cách gọi `new UserId(value)` bên trong.
- Có thể đặt tên theo ý nghĩa nghiệp vụ và tổ chức logic trước khi tạo record.

Một lời gọi constructor trực tiếp cũng hợp lệ:

```java
UserId id = new UserId(" U-100 ");
```

Cả hai cách đều đi qua canonical constructor, vì vậy cùng áp dụng việc kiểm tra và chuẩn hóa `value`.

## 2. Vì sao cần factory method có tên?

Constructor luôn có tên trùng với record. Khi record có nhiều cách tạo mang ý nghĩa khác nhau, các lời gọi `new` có thể khó phân biệt nếu chỉ nhìn vào danh sách đối số.

Ví dụ một khoảng ngày có thể được tạo theo hai quy ước:

- Khoảng đóng: bao gồm cả ngày bắt đầu và ngày kết thúc.
- Khoảng nửa mở: bao gồm ngày bắt đầu nhưng không bao gồm ngày kết thúc.

Nếu cả hai đều nhận hai tham số `LocalDate`, không thể khai báo hai constructor chỉ khác nhau về ý nghĩa nghiệp vụ vì chữ ký kiểu tham số giống nhau.

Factory method giải quyết vấn đề bằng tên:

```java
DateRange.closed(start, end);
DateRange.halfOpen(start, end);
```

Người đọc hiểu quy tắc của khoảng ngay tại nơi gọi. Tuy nhiên, **chỉ đổi tên factory không tự thay đổi ngữ nghĩa của dữ liệu**. Record phải lưu hoặc biểu đạt được quy tắc biên đó; nếu record chỉ có hai component `start` và `end`, hai factory không thể tạo ra hai loại khoảng khác nhau sau khi khởi tạo. Ví dụ, record có thể lưu thêm một component mô tả biên kết thúc:

```java
import java.time.LocalDate;
import java.util.Objects;

public record DateRange(
        LocalDate start,
        LocalDate end,
        boolean endInclusive
) {
    public DateRange {
        start = Objects.requireNonNull(start, "start");
        end = Objects.requireNonNull(end, "end");

        if (start.isAfter(end)) {
            throw new IllegalArgumentException("start must not be after end");
        }
    }

    public static DateRange closed(LocalDate start, LocalDate end) {
        return new DateRange(start, end, true);
    }

    public static DateRange halfOpen(LocalDate start, LocalDate end) {
        return new DateRange(start, end, false);
    }

    public boolean contains(LocalDate date) {
        Objects.requireNonNull(date, "date");
        return !date.isBefore(start)
                && (endInclusive
                    ? !date.isAfter(end)
                    : date.isBefore(end));
    }
}
```

Tên phương thức trở thành một phần của hợp đồng API, còn component `endInclusive` bảo đảm đối tượng lưu được chính sách mà tên factory thể hiện.

Factory có tên đặc biệt hữu ích khi:

- Có nhiều quy tắc tạo đối tượng từ cùng loại tham số.
- Đầu vào đến từ nhiều định dạng khác nhau.
- Có giá trị mặc định mang ý nghĩa nghiệp vụ.
- Việc tạo cần chuyển đổi, chuẩn hóa hoặc kiểm tra bổ sung.
- Cần diễn đạt rõ trạng thái đặc biệt như rỗng, mặc định, không giới hạn hoặc giá trị hệ thống.

## 3. Quy ước đặt tên thường gặp

Tên factory nên mô tả loại đầu vào hoặc ý nghĩa của đối tượng được tạo. Một số tên thường dùng trong Java:

| Tên | Ý nghĩa thường gặp | Ví dụ |
| --- | --- | --- |
| `of(...)` | Tạo từ các giá trị component đã có đúng kiểu đích | `Money.of(amount, currency)` |
| `from(...)` | Chuyển đổi từ một nguồn dữ liệu khác | `UserId.from(externalId)` |
| `parse(...)` | Phân tích chuỗi theo cú pháp xác định | `Version.parse("1.2.0")` |
| `valueOf(...)` | Chuyển đổi giá trị theo quy ước của kiểu | `UserId.valueOf(raw)` |
| `copyOf(...)` | Tạo snapshot hoặc bản sao từ dữ liệu khác | `Labels.copyOf(values)` |
| `empty()` | Tạo giá trị rỗng có ý nghĩa | `SearchFilter.empty()` |
| Tên miền nghiệp vụ | Nêu rõ mục đích tạo | `ServerPort.https()`, `DateRange.singleDay(date)` |

Đây là **quy ước đặt tên**, không phải quy tắc bắt buộc của Java. Hãy dùng tên nhất quán trong cùng API và tránh nhiều tên khác nhau cho cùng một hành vi mà không có lý do rõ ràng.

Một factory method có thể được overload như phương thức Java thông thường, nhưng không nên tạo quá nhiều chữ ký gần giống nhau khiến người gọi khó chọn.

## 4. Ví dụ: DateRange với các cách tạo có ý nghĩa

Ở ví dụ này, xét một record đơn giản chỉ biểu diễn khoảng ngày đóng, trong đó ngày bắt đầu và kết thúc đều được tính vào khoảng. Ta có thể đặt bất biến chung trong canonical constructor và tạo các factory diễn đạt từng trường hợp:

```java
import java.time.Clock;
import java.time.LocalDate;
import java.util.Objects;

public record DateRange(LocalDate start, LocalDate end) {

    public DateRange {
        start = Objects.requireNonNull(start, "start");
        end = Objects.requireNonNull(end, "end");

        if (start.isAfter(end)) {
            throw new IllegalArgumentException(
                    "start must not be after end"
            );
        }
    }

    public static DateRange closed(
            LocalDate start,
            LocalDate end
    ) {
        return new DateRange(start, end);
    }

    public static DateRange singleDay(LocalDate date) {
        Objects.requireNonNull(date, "date");
        return new DateRange(date, date);
    }

    public static DateRange today() {
        return singleDay(LocalDate.now());
    }
}
```

Cách sử dụng:

```java
DateRange projectPeriod = DateRange.closed(
        LocalDate.of(2026, 1, 1),
        LocalDate.of(2026, 3, 31)
);

DateRange releaseDay = DateRange.singleDay(
        LocalDate.of(2026, 4, 15)
);

DateRange currentDay = DateRange.today();
```

Các tên `closed`, `singleDay` và `today` nói rõ mục đích tạo đối tượng. Factory `today()` lấy ngày hiện tại theo múi giờ mặc định của JVM thông qua `LocalDate.now()`. Nếu nghiệp vụ cần múi giờ cụ thể, nên nhận `Clock` hoặc `ZoneId` từ bên ngoài để kết quả dễ dự đoán và kiểm thử.

Ví dụ factory có nhận Clock:

```java
public static DateRange today(Clock clock) {
    Objects.requireNonNull(clock, "clock");
    LocalDate date = LocalDate.now(clock);
    return singleDay(date);
}
```

Đây là phần phương thức bổ sung bên trong record `DateRange` ở ví dụ trên; các import `Clock`, `LocalDate` và `Objects` đã có trong khai báo đó. Khi truyền `Clock.fixed(...)` trong test, kết quả không phụ thuộc ngày thực tế của máy chạy.

## 5. Phân biệt of, from và parse qua ví dụ

Ba tên `of`, `from` và `parse` thường thể hiện ba ý định khác nhau.

### of: đầu vào đã có dạng component

```java
public record UserId(String value) {

    public UserId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is required");
        }
        value = value.strip();
    }

    public static UserId of(String value) {
        return new UserId(value);
    }
}
```

`of` nhận trực tiếp giá trị cùng kiểu với component `String`.

### from: chuyển đổi từ một kiểu nguồn

```java
public record UserId(String value) {

    public UserId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is required");
        }
        value = value.strip();
    }

    public static UserId from(long numericId) {
        if (numericId < 0) {
            throw new IllegalArgumentException("id must be non-negative");
        }

        return new UserId(Long.toString(numericId));
    }
}
```

`from` diễn tả việc chuyển số sang biểu diễn `String` của `UserId`. Quy tắc không cho phép ID âm thuộc riêng nguồn đầu vào này, còn bất biến chung về giá trị chuỗi vẫn được canonical constructor kiểm tra.

### parse: phân tích một định dạng văn bản

```java
public record UserId(String value) {

    public UserId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is required");
        }
        value = value.strip();
    }

    public static UserId parse(String text) {
        if (text == null) {
            throw new IllegalArgumentException("text is required");
        }

        String prefix = "user:";
        String normalized = text.strip();

        if (!normalized.startsWith(prefix)) {
            throw new IllegalArgumentException(
                    "expected format user:<id>"
            );
        }

        return new UserId(normalized.substring(prefix.length()));
    }
}
```

Sử dụng:

```java
UserId direct = UserId.of("U-100");
UserId converted = UserId.from(100L);
UserId parsed = UserId.parse("user:U-100");

System.out.println(direct.value());    // U-100
System.out.println(converted.value()); // 100
System.out.println(parsed.value());    // U-100
```

Các factory cùng trả về `UserId` nhưng có hợp đồng đầu vào khác nhau. `parse` kiểm tra cú pháp văn bản; `from` chuyển đổi kiểu; `of` nhận giá trị đã ở dạng component.

Không cần ép mọi record phải có đủ các tên này. Chỉ tạo factory khi có một cách tạo có ý nghĩa riêng.

## 6. Đặt bất biến chung ở canonical constructor

Factory method không nên trở thành nơi duy nhất bảo vệ dữ liệu nếu record có thể được khởi tạo trực tiếp bằng `new`.

Ví dụ:

```java
public record PageRequest(int page, int size) {

    public PageRequest {
        if (page < 1) {
            throw new IllegalArgumentException("page must be >= 1");
        }
        if (size < 1 || size > 200) {
            throw new IllegalArgumentException(
                    "size must be between 1 and 200"
            );
        }
    }

    public static PageRequest firstPage(int size) {
        return new PageRequest(1, size);
    }

    public static PageRequest of(int page, int size) {
        return new PageRequest(page, size);
    }

    public static PageRequest defaults() {
        return new PageRequest(1, 20);
    }
}
```

Các cách tạo:

```java
PageRequest first = PageRequest.firstPage(50);
PageRequest custom = PageRequest.of(3, 25);
PageRequest defaults = PageRequest.defaults();
```

Canonical constructor đảm bảo mọi đối tượng `PageRequest` đều có `page` và `size` hợp lệ, kể cả khi người gọi viết `new PageRequest(0, 10)` trực tiếp.

Factory có thể kiểm tra thêm điều kiện đặc thù của nguồn đầu vào, nhưng không nên lặp lại toàn bộ bất biến chung ở từng factory. Điều này tránh tình trạng một đường tạo kiểm tra dữ liệu, đường khác lại bỏ sót.

## 7. Factory method có thể chuẩn hóa hoặc chuyển đổi trước khi gọi constructor

Một factory có thể làm rõ một chính sách chuyển đổi cụ thể trước khi tạo record:

```java
import java.util.Locale;
import java.util.Objects;

public record CountryCode(String value) {

    public CountryCode {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z]{2}")) {
            throw new IllegalArgumentException(
                    "country code must contain two ASCII letters"
            );
        }
    }

    public static CountryCode fromUserInput(String input) {
        return new CountryCode(input);
    }

    public static CountryCode parseStrict(String input) {
        Objects.requireNonNull(input, "input");

        if (!input.matches("[A-Za-z]{2}")) {
            throw new IllegalArgumentException(
                    "expected exactly two ASCII letters"
            );
        }

        return new CountryCode(input);
    }
}
```

Hai factory có mục đích khác nhau:

- `fromUserInput` chấp nhận khoảng trắng hai đầu và chữ thường vì canonical constructor chuẩn hóa.
- `parseStrict` yêu cầu chuỗi đầu vào có đúng hai chữ cái ASCII trước khi chuyển đến canonical constructor.

Sau đó canonical constructor vẫn áp dụng bất biến chung. Factory kiểm tra yêu cầu riêng của nguồn dữ liệu; canonical constructor bảo vệ trạng thái cuối cùng của record.

## 8. Factory cho giá trị mặc định và trạng thái đặc biệt

Factory method có tên đặc biệt hữu ích khi một giá trị mặc định có ý nghĩa nghiệp vụ. Ví dụ:

```java
public record ServerPort(int value) {

    public ServerPort {
        if (value < 1 || value > 65535) {
            throw new IllegalArgumentException("invalid port");
        }
    }

    public static ServerPort http() {
        return new ServerPort(80);
    }

    public static ServerPort https() {
        return new ServerPort(443);
    }

    public static ServerPort of(int value) {
        return new ServerPort(value);
    }
}
```

Sử dụng:

```java
ServerPort web = ServerPort.http();
ServerPort secureWeb = ServerPort.https();
ServerPort custom = ServerPort.of(8443);
```

Tên `http()` và `https()` thể hiện ý nghĩa nghiệp vụ rõ hơn `new ServerPort(80)` hoặc `new ServerPort(443)`.

Không nên dùng factory tên `default()` hoặc `empty()` nếu khái niệm mặc định/rỗng không rõ nghĩa trong miền dữ liệu. Tên phải giúp người gọi hiểu giá trị được tạo đại diện cho điều gì.

## 9. Factory method với collection: copyOf

Khi record lưu một collection, factory `copyOf` có thể diễn đạt rõ rằng dữ liệu đầu vào được chụp thành một bản sao không thể sửa đổi qua API collection thông thường.

```java
import java.util.List;
import java.util.Objects;

public record Labels(List<String> values) {

    public Labels {
        values = List.copyOf(
                Objects.requireNonNull(values, "values")
        );
    }

    public static Labels copyOf(Iterable<String> source) {
        Objects.requireNonNull(source, "source");

        java.util.ArrayList<String> copy = new java.util.ArrayList<>();
        for (String value : source) {
            copy.add(value);
        }

        return new Labels(copy);
    }

    public static Labels empty() {
        return new Labels(List.of());
    }
}
```

Sử dụng:

```java
Labels labels = Labels.copyOf(List.of("java", "record"));
Labels none = Labels.empty();
```

Canonical constructor vẫn dùng `List.copyOf` để bảo vệ mọi đường khởi tạo, kể cả `new Labels(mutableList)`. Factory `copyOf` mở rộng kiểu nguồn thành `Iterable`, sao chép dữ liệu và tạo record. `empty` diễn đạt trạng thái không có nhãn.

`List.copyOf` tạo danh sách không thể sửa đổi và không chấp nhận phần tử null. Đây là sao chép cấu trúc nông; nếu phần tử là đối tượng mutable, trạng thái bên trong phần tử vẫn có thể thay đổi. Nếu cần bất biến sâu, phải thiết kế thêm cho kiểu phần tử.

## 10. Factory method có thể trả về interface hoặc kiểu trừu tượng

Một static factory method không bắt buộc phải trả về chính kiểu record khai báo nó. Nó có thể trả về một interface hoặc kiểu cha mà record triển khai. Nếu interface là một phần API công khai, khai báo nó trong file riêng:

```java
// File: Identifier.java
public interface Identifier {
    String value();
}
```

Record triển khai interface và có factory trả về abstraction:

```java
// File: UserId.java
import java.util.Objects;

public record UserId(String value) implements Identifier {

    public UserId {
        value = Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException("value is required");
        }
    }

    public static Identifier from(String raw) {
        return new UserId(raw);
    }
}
```

Người gọi có thể phụ thuộc vào hợp đồng `Identifier`:

```java
Identifier id = UserId.from("U-100");
System.out.println(id.value());
```

Cách này hữu ích khi API muốn trả về abstraction thay vì buộc người gọi phụ thuộc kiểu triển khai. Tuy nhiên, `UserId` vẫn là public record và canonical constructor công khai vẫn có thể được gọi trực tiếp. Việc trả về interface không tự ẩn hoặc khóa constructor của record.

## 11. Giới hạn quan trọng: factory không bắt buộc người gọi dùng factory

Một `public record` phải có canonical constructor với mức truy cập ít nhất rộng bằng mức truy cập của record. Do đó, public record không thể dùng canonical constructor `private` để buộc mọi bên gọi phải đi qua static factory.

Ví dụ:

```java
public record UserId(String value) {

    public UserId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is required");
        }
    }

    public static UserId guest() {
        return new UserId("guest");
    }
}
```

Cả hai cách đều có thể được gọi:

```java
UserId a = UserId.guest();
UserId b = new UserId("admin");
```

Factory `guest()` cung cấp một cách tạo có tên và ý nghĩa. Nó không cấm bên gọi sử dụng canonical constructor trực tiếp.

Nếu yêu cầu thiết kế là kiểm soát tuyệt đối việc tạo đối tượng, dùng cache để đảm bảo một instance duy nhất, hoặc buộc mọi lần tạo đi qua một quy trình riêng, class thông thường với constructor có quyền truy cập phù hợp có thể là lựa chọn tốt hơn. Record phù hợp khi mô hình dữ liệu giá trị và canonical construction công khai là điều chấp nhận được.

## 12. Phân biệt static factory method với Factory Method pattern

Hai thuật ngữ dễ bị nhầm:

- **Static factory method:** một phương thức tĩnh trả về một đối tượng, ví dụ `UserId.parse(text)`.
- **Factory Method pattern:** một mẫu thiết kế hướng đối tượng, trong đó việc tạo sản phẩm được ủy quyền cho các phương thức có thể được lớp con triển khai hoặc thay đổi theo cấu trúc thiết kế.

Bài này nói về static factory method như một kỹ thuật thiết kế API Java. Không cần tạo hệ thống lớp factory riêng hoặc áp dụng Factory Method pattern chỉ để tạo một record.

Một static factory method thường đủ khi:

- Việc tạo chỉ cần chuyển đổi hoặc xác thực đầu vào.
- Các biến thể tạo có tên rõ ràng.
- Không cần một họ lớp sản phẩm hoặc cơ chế thay thế triển khai phức tạp.

## 13. So sánh constructor, overload và static factory

| Tiêu chí | Constructor trực tiếp | Constructor overload | Static factory có tên |
| --- | --- | --- | --- |
| Cách gọi | `new UserId(value)` | `new UserId(id)` | `UserId.from(id)` |
| Tên biểu đạt ý nghĩa | Chỉ dùng tên record | Vẫn dùng tên record | Có tên riêng theo nghiệp vụ |
| Phân biệt hai cách tạo cùng kiểu tham số | Không thể chỉ khác ý nghĩa | Không thể trùng chữ ký | Có thể dùng hai tên khác nhau |
| Giá trị mặc định | Có thể truyền trong overload | Phù hợp giá trị mặc định đơn giản | Có thể đặt tên như `defaults()` |
| Chuyển đổi đầu vào | Thực hiện trong constructor | Thường ủy quyền đến canonical | Thực hiện trước khi gọi constructor |
| Trả về interface | Không | Không | Có |
| Kiểm soát canonical constructor của public record | Không | Không | Không; factory không khóa `new` |

Ví dụ hai ý nghĩa khác nhau nhưng cùng kiểu đầu vào:

```java
DateRange.closed(start, end);
DateRange.halfOpen(start, end);
```

Nếu dùng constructor, hai cách này đều có chữ ký `DateRange(LocalDate, LocalDate)` nên không thể khai báo đồng thời. Factory method giải quyết bằng tên có ý nghĩa.

## 14. Nguyên tắc thiết kế factory method tốt

Một factory method tốt nên có các đặc điểm:

1. **Tên nói lên ý định:** `parse` cho văn bản, `from` cho chuyển đổi, `of` cho giá trị đã có dạng đích, hoặc tên nghiệp vụ cụ thể.
2. **Hợp đồng đầu vào rõ ràng:** mô tả chấp nhận null hay không, định dạng, miền giá trị và chính sách chuẩn hóa.
3. **Không lặp bất biến chung:** canonical constructor vẫn là nơi bảo vệ trạng thái cuối cùng của record.
4. **Không gây bất ngờ:** factory không âm thầm làm mất thông tin hoặc trả về trạng thái khác với tên gọi.
5. **Giữ số lượng hợp lý:** chỉ thêm factory khi có ý nghĩa tạo riêng biệt.
6. **Kiểm thử được:** xác minh component được lưu, ngoại lệ và các giá trị biên.

Không nên tạo nhiều tên factory chỉ để gọi cùng một constructor mà không có khác biệt về hợp đồng hoặc ý nghĩa. API có quá nhiều lựa chọn tương tự sẽ khó học và khó bảo trì.

## 15. Kiểm thử factory method

Kiểm thử nên xác nhận factory tạo đúng component và canonical constructor vẫn áp dụng validation.

Ví dụ JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ServerPortTest {

    @Test
    void namedFactoriesUseExpectedPorts() {
        assertEquals(80, ServerPort.http().value());
        assertEquals(443, ServerPort.https().value());
    }

    @Test
    void customFactoryUsesCanonicalValidation() {
        assertEquals(8443, ServerPort.of(8443).value());

        assertThrows(
                IllegalArgumentException.class,
                () -> ServerPort.of(0)
        );
    }
}
```

Với `DateRange`, nên kiểm tra:

- `closed(start, end)` giữ đúng hai đầu mút.
- `singleDay(date)` tạo khoảng có start bằng end.
- `today(Clock)` cho kết quả ổn định khi dùng clock cố định.
- Ngày null hoặc start sau end bị từ chối bởi canonical constructor.

Với factory `parse` hoặc `from`, kiểm tra thêm định dạng sai, dữ liệu null và trường hợp chuyển đổi biên. Đừng chỉ kiểm tra factory trả về một đối tượng; hãy kiểm tra các accessor thể hiện đúng dữ liệu đã được chuẩn hóa.

## 16. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng factory tên `of` cho một phép parse phức tạp | Ý định của lời gọi không rõ. | Dùng `parse` khi xử lý cú pháp văn bản. |
| Factory tự xác thực nhưng canonical constructor không bảo vệ dữ liệu | Người gọi có thể bỏ qua factory và gọi `new` trực tiếp. | Đặt bất biến chung trong canonical constructor. |
| Lặp toàn bộ validation ở mọi factory | Quy tắc dễ lệch nhau khi thay đổi. | Chỉ kiểm tra điều kiện đặc thù nguồn; ủy quyền constructor chuẩn. |
| Nghĩ factory khóa được constructor public | Bên gọi vẫn có thể gọi canonical constructor. | Dùng class thường nếu cần kiểm soát quyền tạo đối tượng. |
| Tạo quá nhiều factory có cùng ý nghĩa | API khó học và khó bảo trì. | Giữ những factory có hợp đồng khác biệt rõ ràng. |
| Dùng tên không nói lên quy tắc dữ liệu | Người gọi phải đọc implementation mới hiểu. | Đặt tên theo nguồn hoặc ý nghĩa nghiệp vụ. |
| Factory âm thầm làm tròn hoặc bỏ dữ liệu | Kết quả có thể gây bất ngờ. | Công bố chính sách chuyển đổi và kiểm thử biên. |
| Nhầm static factory method với Factory Method pattern | Dẫn đến thiết kế lớp factory không cần thiết. | Dùng static factory đơn giản khi chỉ cần tạo record. |

## 17. Bài tập tự luyện

### Bài 1: Chọn tên factory

Một record `Version` có component `major`, `minor` và `patch`. Bạn cần:

- Tạo từ ba số nguyên đã có: tên nào phù hợp?
- Chuyển từ một chuỗi như `"1.2.3"`: tên nào phù hợp?
- Tạo phiên bản ban đầu của ứng dụng: tên nào phù hợp?

**Đáp án gợi ý:**

- `Version.of(1, 2, 3)` cho các component đã có dạng đích.
- `Version.parse("1.2.3")` cho đầu vào văn bản cần phân tích.
- `Version.initial()` hoặc `Version.firstRelease()` nếu đó là khái niệm nghiệp vụ được định nghĩa rõ.

### Bài 2: Viết factory có tên

Cho record `ServerPort(int value)` với miền giá trị từ 1 đến 65535. Viết factory `http()`, `https()` và `of(int value)`.

**Đáp án tham khảo:**

```java
public record ServerPort(int value) {
    public ServerPort {
        if (value < 1 || value > 65535) {
            throw new IllegalArgumentException("invalid port");
        }
    }

    public static ServerPort http() {
        return new ServerPort(80);
    }

    public static ServerPort https() {
        return new ServerPort(443);
    }

    public static ServerPort of(int value) {
        return new ServerPort(value);
    }
}
```

### Bài 3: Vì sao validation phải nằm ở canonical constructor?

Một record có factory `of(String value)` kiểm tra null, nhưng canonical constructor không kiểm tra gì. Người gọi khác dùng `new MyValue(null)`.

**Đáp án:** Đối tượng không hợp lệ vẫn được tạo qua constructor trực tiếp. Đặt bất biến chung trong canonical constructor để cả factory lẫn `new` đều đi qua cùng kiểm tra.

### Bài 4: Factory có khóa được constructor không?

Với `public record UserId(String value)`, khai báo `public static UserId of(String value)` có buộc mọi bên gọi phải dùng `UserId.of(value)` không?

**Đáp án:** Không. Public record phải có canonical constructor truy cập được ít nhất như record. Factory tạo cách gọi có tên nhưng không thể làm canonical constructor thành private.

## Ghi nhớ

Static factory method giúp record diễn đạt nhiều cách tạo có ý nghĩa nghiệp vụ bằng tên rõ ràng như `of`, `from`, `parse`, `copyOf` hoặc tên miền cụ thể. Factory có thể chuyển đổi đầu vào, cung cấp giá trị mặc định và trả về abstraction. Hãy giữ bất biến chung trong canonical constructor để mọi đường tạo đều được bảo vệ. Với public record, factory không khóa được canonical constructor; nếu cần kiểm soát quyền tạo đối tượng, hãy cân nhắc class thông thường.

## Tài liệu tham khảo

- [Java Language Specification — Java SE 16, `8.10` Record Classes](https://docs.oracle.com/javase/specs/jls/se16/html/jls-8.html#jls-8.10).
- [Java Language Specification — Java SE 26, `8.10` Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [Java API — LocalDate](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html).
- [Java API — Clock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Clock.html).
- [Effective Java, Item 1 — Consider static factory methods instead of constructors](https://www.oreilly.com/library/view/effective-java/9780134686097/).
- [JEP 395 — Records (hoàn thiện trong Java 16)](https://openjdk.org/jeps/395).
