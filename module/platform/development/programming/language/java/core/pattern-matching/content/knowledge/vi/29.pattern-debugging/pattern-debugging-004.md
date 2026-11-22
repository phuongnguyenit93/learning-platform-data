# Phân tích vì sao pattern không match trong Java 21

## Mục tiêu

Trong chủ đề **Debugging**, một biểu thức pattern matching trả `false` hoặc một nhánh `switch` không được chọn không có nghĩa là trình biên dịch hoặc JVM bị lỗi. Thường có nhiều “cổng” phải đi qua: kiểu của selector phải phù hợp, record ở các tầng lồng nhau phải tồn tại, các component patterns phải khớp, và cuối cùng guard nghiệp vụ phải đúng. Chỉ cần một cổng không đạt là nhánh mong đợi không chạy.

Bài học này hướng dẫn cách **phân tích vì sao pattern không match** một cách có hệ thống, tách lỗi **compile time** khỏi thất bại **runtime**, kiểm tra đúng vị trí `null`, chẩn đoán guard `when` và biểu thức `instanceof` với `&&`, đồng thời xây bộ test có kết quả mong đợi độc lập.

Sau bài này, bạn có thể:

- Xác định pattern **không áp dụng được ở compile time**, **không match về cấu trúc ở runtime**, hay **đã match cấu trúc nhưng guard trả false**.
- Chẩn đoán selector `null`, sai kiểu, nested record `null` và component lá `null`.
- Xem thứ tự `case`, `when`, giá trị enum/string, điều kiện biên và cách so sánh chuỗi.
- Viết một phương thức chẩn đoán tách các điều kiện ra từng bước mà **không làm thay đổi logic đang vận hành**.
- Dùng test để xác nhận cả nhánh chọn, nguyên nhân từ chối và hành vi `null`.

**Phiên bản:** Java 21 trở lên. Type patterns cho `instanceof` ổn định từ Java 16 (JEP 394); record patterns (JEP 440) và pattern matching cho `switch` (JEP 441) là tính năng chính thức từ Java 21. Ví dụ dùng `javac --release 21`, không cần `--enable-preview`.

## 1. Quy trình tư duy: kiểm tra từ ngoài vào trong

Với một pattern phức tạp, hãy xét theo bốn tầng:

| Tầng | Câu hỏi | Nếu không thỏa |
|---|---|---|
| **Compile time** | Pattern có applicable với kiểu tĩnh của biểu thức không, và nhánh `switch` có hợp lệ không? | `javac` báo lỗi; đây **không** phải một lần runtime no-match |
| **Root type / null** | Selector có khác `null` và là kiểu record/class mà pattern yêu cầu không? | `instanceof` trả false; `switch` xét nhánh phù hợp khác hoặc xử lý null |
| **Nested structure** | Mỗi nested record có khác `null` và các component patterns có khớp không? | Toàn bộ record pattern không khớp, ngay cả khi root đúng kiểu |
| **Guard / điều kiện thêm** | Sau khi bind biến, biểu thức `when` hoặc vế phải `&&` có đúng không? | Pattern đã có thể khớp về cấu trúc nhưng nhánh có guard vẫn bị bỏ qua |

Một cổng “no-match” không tự cung cấp thông báo nguyên nhân. `instanceof` chỉ trả về `boolean`, còn `switch` chọn nhánh phù hợp đầu tiên; muốn biết *tại sao*, bạn phải xây dữ liệu quan sát hoặc một hàm chẩn đoán rõ ràng.

**Quy tắc debug hữu ích:** đi từ selector đến từng tầng component, rồi mới kiểm tra điều kiện nghiệp vụ. Đừng sửa guard khi thực ra nested record đã bằng `null` và guard chưa hề được đánh giá.

## 2. Ví dụ domain: một Ticket ưu tiên

Giả sử có các record:

```java
record Address(String city, String country) {}
record Customer(String name, Address address) {}
record Ticket(String id, Customer customer, int severity, boolean active) {}
```

Bài dùng một **chính sách giả định để học**: Ticket được phân loại `PRIORITY` khi đồng thời:

1. Root là `Ticket` và có nested `Customer`, `Address` khác `null`.
2. `active == true`.
3. `severity >= 3`.
4. `country` đúng bằng `"VN"`.
5. `city` khác null và bằng `"HCM"` nếu bỏ qua khác biệt chữ hoa/thường.

Mọi `Ticket` không đạt các điều kiện trên được phân loại `STANDARD:<id>`; input `null` trả `ROOT_NULL`; input không phải Ticket trả `OTHER_TYPE`. Đây là contract rõ ràng để viết test.

Nhánh `switch` tương ứng:

```java
case Ticket(var id,
            Customer(var name, Address(var city, var country)),
            var severity, var active)
        when active && severity >= 3
             && "VN".equals(country)
             && city != null
             && city.equalsIgnoreCase("HCM")
        -> "PRIORITY:" + id;
```

**Đây là một case label minh họa**, chưa phải chương trình hoàn chỉnh. Có hai lý do chính khiến nó không được chọn:

- **Pattern không match cấu trúc:** root sai kiểu/null; `Customer(...)` hoặc `Address(...)` trỏ tới null; hoặc component pattern tương ứng không khớp.
- **Pattern đã match cấu trúc nhưng guard false:** Ticket inactive, severity thấp, country khác VN, city null hoặc khác HCM.

Trong bản này `var id` và `var name` **không kiểm tra non-null**. Record components kiểu tham chiếu có thể bind `null` khi dùng `var` trực tiếp. Do đó `id == null` hay `name == null` không nhất thiết là lý do khiến pattern thất bại.

## 3. Root null và sai kiểu: nhìn giống nhau, nhưng cần phân biệt

Với biểu thức `instanceof`:

```java
Object input = null;
boolean a = input instanceof Ticket ticket; // false
boolean b = input instanceof Ticket(var id, var customer,
                                    var severity, var active); // false
```

Khi selector bằng null, `instanceof` trả false. Pattern variable không được bind và guard ở vế phải `&&` sẽ không được thực thi.

Khi selector là `"text"` nhưng ta kiểm tra `Ticket`, biểu thức cũng trả false. Hai trường hợp này có cùng boolean nhưng khác nguyên nhân:

```java
if (input == null) {
    System.out.println("root-null");
} else if (!(input instanceof Ticket ticket)) {
    System.out.println("wrong-type");
} else {
    System.out.println("ticket-id=" + ticket.id());
}
```

Đây là **snippet minh họa trong method**. Mẫu if này giúp giữ thông tin chẩn đoán: null khác với giá trị sai kiểu.

Với pattern `switch` Java 21, cần xử lý selector null tường minh nếu muốn thông điệp riêng:

```java
return switch (input) {
    case null -> "ROOT_NULL";
    case Ticket t -> "TICKET:" + t.id();
    default -> "OTHER_TYPE";
};
```

`default` thông thường không tự bắt selector null trong pattern switch. Nếu bỏ `case null`, chương trình có thể ném `NullPointerException` khi selector null thay vì đi vào default. Điều này khác với `instanceof`, vốn trả false với null root.

## 4. Nested record null: lý do rất dễ bị bỏ sót

Hai record patterns nhìn có vẻ giống nhau nhưng khác về độ sâu kiểm tra:

```java
input instanceof Ticket(var id, var customer, var severity, var active)
```

và

```java
input instanceof Ticket(
        var id,
        Customer(var name, Address(var city, var country)),
        var severity, var active)
```

Ở biểu thức thứ nhất, `var customer` trực tiếp nhận component kiểu `Customer`, **có thể bind `null`**. Ở biểu thức thứ hai, compiler/JVM phải khớp tiếp `Customer(...)` và `Address(...)`. Nested record pattern **không khớp null**.

| Input | Shallow Ticket pattern | Deep Ticket → Customer → Address |
|---|---|---|
| `null` | Không khớp | Không khớp |
| `"text"` | Không khớp | Không khớp |
| `new Ticket("T1", null, 4, true)` | Khớp | Không khớp |
| `Ticket` có Customer nhưng Address null | Khớp | Không khớp |
| `Ticket` có Address(city=null, country="VN") | Khớp | **Khớp về cấu trúc**, guard có thể sai |
| `Ticket` có Address(city="HCM", country=null) | Khớp | **Khớp về cấu trúc**, guard có thể sai |
| `Ticket` có ID null và nested records đầy đủ | Khớp | Khớp (nếu component khác đáp ứng) |

**Lưu ý về component lá:** `var city` và `var country` có thể bind null nếu bản thân record `Address` tồn tại. Không nên kết luận “record pattern luôn loại trừ mọi null bên trong”. Nó chỉ yêu cầu record tại **tầng được deconstruct** khác null; nullable leaf vẫn cần guard.

Khi xem debugger, có thể kiểm tra chính xác các đường:

```java
ticket.customer() == null
ticket.customer().address() == null
```

Nhưng **không thực thi dòng thứ hai** khi dòng thứ nhất đúng, nếu không sẽ tạo NPE trong quá trình debug. Thứ tự an toàn: root → Customer → Address → city/country.

## 5. Guard false khác với pattern không khớp

Trong một `case` có `when`, guard chỉ được xem xét **sau** khi pattern chính đã khớp và các biến được bind. Vì vậy:

```java
case Ticket(var id,
            Customer(var name, Address(var city, var country)),
            var severity, var active)
        when active && severity >= 3
             && "VN".equals(country)
             && city != null
             && city.equalsIgnoreCase("HCM")
        -> "PRIORITY:" + id;
```

có thể bỏ qua nhánh do:

- `active` false;
- `severity` là 2 (dưới ngưỡng 3);
- `country` khác chính xác `"VN"`, hoặc null;
- `city` null hoặc khác `"HCM"` theo quy tắc `equalsIgnoreCase`.

Nếu một phép thử về quốc gia sai, phần `city` phía sau không được chạy vì `&&` short-circuit. Điều này không ảnh hưởng kết quả boolean cuối, nhưng **ảnh hưởng cách diễn giải trace**: log nằm ở điều kiện cuối có thể không bao giờ chạy, không đủ để khẳng định chương trình chưa tới guard.

### So sánh chuỗi cần khớp đúng chính sách

- `"VN".equals(country)` phân biệt hoa/thường và an toàn với `null`.
- `city.equalsIgnoreCase("HCM")` bỏ qua hoa/thường nhưng **không tự trim**. Giá trị `" HCM "` vẫn không bằng `"HCM"`.
- `city != null` phải đứng trước lời gọi `city.equalsIgnoreCase(...)`.
- `severity >= 3` chấp nhận đúng mốc 3; đổi thành `> 3` làm đổi hành vi ở ngưỡng.
- Nếu API nguồn dùng mã thành phố khác, không được tự suy diễn rằng `"HCM"`, `"Ho Chi Minh"` và mã nội bộ là như nhau. Cần quy định chuẩn hóa ở boundary nếu nghiệp vụ yêu cầu.

Debug guard bằng **giá trị thực tế sau bind**, không chỉ bằng cách nhìn tên biến trong code.

## 6. Chương trình Java 21 đầy đủ: phân loại, chẩn đoán và đối chiếu

Tạo tệp **`PatternMismatchDiagnosticsDemo.java`** với mã sau. Chương trình có ba phương thức:

- `isPriority` là phép kiểm tra `instanceof` với nested record pattern và `&&`.
- `route` là `switch` có một nhánh guarded, một nhánh Ticket fallback, một nhánh null và một default cho sai kiểu.
- `diagnose` kiểm tra từng điều kiện theo tên, trả về một lý do có thể đọc được.

`check` so kết quả của ba phương thức với expected độc lập và ném `AssertionError` nếu có sai lệch.

```java
import java.util.Objects;

public class PatternMismatchDiagnosticsDemo {
    record Address(String city, String country) {}
    record Customer(String name, Address address) {}
    record Ticket(String id, Customer customer, int severity, boolean active) {}

    static boolean isPriority(Object input) {
        return input instanceof Ticket(
                var id,
                Customer(var name, Address(var city, var country)),
                var severity, var active)
                && active
                && severity >= 3
                && "VN".equals(country)
                && city != null
                && city.equalsIgnoreCase("HCM");
    }

    static String route(Object input) {
        return switch (input) {
            case null -> "ROOT_NULL";
            case Ticket(var id,
                        Customer(var name, Address(var city, var country)),
                        var severity, var active)
                    when active && severity >= 3
                         && "VN".equals(country)
                         && city != null
                         && city.equalsIgnoreCase("HCM")
                    -> "PRIORITY:" + id;
            case Ticket ticket -> "STANDARD:" + ticket.id();
            default -> "OTHER_TYPE";
        };
    }

    static String diagnose(Object input) {
        if (input == null) return "root-null";
        if (!(input instanceof Ticket ticket)) return "wrong-type";
        if (ticket.customer() == null) return "customer-null";
        Customer customer = ticket.customer();
        if (customer.address() == null) return "address-null";
        Address address = customer.address();
        if (!ticket.active()) return "inactive";
        if (ticket.severity() < 3) return "low-severity";
        if (!"VN".equals(address.country())) {
            return address.country() == null ? "country-null" : "country-other";
        }
        if (address.city() == null) return "city-null";
        if (!address.city().equalsIgnoreCase("HCM")) return "city-other";
        return "matched";
    }

    static void check(String label, Object input, String expectedRoute,
                      String expectedReason, boolean expectedPriority) {
        String actualRoute = route(input);
        String actualReason = diagnose(input);
        boolean actualPriority = isPriority(input);
        if (!Objects.equals(expectedRoute, actualRoute)
                || !Objects.equals(expectedReason, actualReason)
                || expectedPriority != actualPriority) {
            throw new AssertionError(label + ": route=" + actualRoute
                    + ", reason=" + actualReason
                    + ", priority=" + actualPriority);
        }
        System.out.println(label + " => " + actualRoute
                + " | " + actualReason + " | priority=" + actualPriority);
    }

    public static void main(String[] args) {
        check("root null", null, "ROOT_NULL", "root-null", false);
        check("wrong type", "text", "OTHER_TYPE", "wrong-type", false);
        check("customer null", new Ticket("T01", null, 4, true),
                "STANDARD:T01", "customer-null", false);
        check("address null", new Ticket("T02", new Customer("An", null), 4, true),
                "STANDARD:T02", "address-null", false);
        check("inactive", new Ticket("T03", new Customer("An",
                new Address("HCM", "VN")), 4, false),
                "STANDARD:T03", "inactive", false);
        check("low severity", new Ticket("T04", new Customer("An",
                new Address("HCM", "VN")), 2, true),
                "STANDARD:T04", "low-severity", false);
        check("country null", new Ticket("T05", new Customer("An",
                new Address("HCM", null)), 4, true),
                "STANDARD:T05", "country-null", false);
        check("country other", new Ticket("T06", new Customer("An",
                new Address("HCM", "TH")), 4, true),
                "STANDARD:T06", "country-other", false);
        check("city null", new Ticket("T07", new Customer("An",
                new Address(null, "VN")), 4, true),
                "STANDARD:T07", "city-null", false);
        check("city other", new Ticket("T08", new Customer("An",
                new Address("HN", "VN")), 4, true),
                "STANDARD:T08", "city-other", false);
        check("city lowercase", new Ticket("T09", new Customer("An",
                new Address("hcm", "VN")), 4, true),
                "PRIORITY:T09", "matched", true);
        check("boundary severity", new Ticket("T10", new Customer("An",
                new Address("HCM", "VN")), 3, true),
                "PRIORITY:T10", "matched", true);
        check("id null", new Ticket(null, new Customer("An",
                new Address("HCM", "VN")), 4, true),
                "PRIORITY:null", "matched", true);
        check("name null", new Ticket("T11", new Customer(null,
                new Address("HCM", "VN")), 4, true),
                "PRIORITY:T11", "matched", true);
        check("high severity", new Ticket("T12", new Customer("An",
                new Address("HCM", "VN")), 9, true),
                "PRIORITY:T12", "matched", true);
    }
}
```

Biên dịch và chạy bằng JDK 21 hoặc mới hơn:

```bash
javac --release 21 PatternMismatchDiagnosticsDemo.java
java PatternMismatchDiagnosticsDemo
```

**Stdout đã kiểm tra bằng chương trình chạy thực tế:**

```text
root null => ROOT_NULL | root-null | priority=false
wrong type => OTHER_TYPE | wrong-type | priority=false
customer null => STANDARD:T01 | customer-null | priority=false
address null => STANDARD:T02 | address-null | priority=false
inactive => STANDARD:T03 | inactive | priority=false
low severity => STANDARD:T04 | low-severity | priority=false
country null => STANDARD:T05 | country-null | priority=false
country other => STANDARD:T06 | country-other | priority=false
city null => STANDARD:T07 | city-null | priority=false
city other => STANDARD:T08 | city-other | priority=false
city lowercase => PRIORITY:T09 | matched | priority=true
boundary severity => PRIORITY:T10 | matched | priority=true
id null => PRIORITY:null | matched | priority=true
name null => PRIORITY:T11 | matched | priority=true
high severity => PRIORITY:T12 | matched | priority=true
```

**Giải thích các trường hợp đáng chú ý:**

1. **Root null**: `instanceof` trả false; `switch` chọn `case null`; `diagnose` báo root-null.
2. **Sai kiểu**: input là String, không phải Ticket; `default` trong `switch` xử lý kiểu khác.
3. **Customer null**: Ticket tồn tại, nhưng `Customer(...)` không khớp; nhánh guarded của `switch` bị bỏ qua và `case Ticket ticket` trả STANDARD.
4. **Address null**: tương tự, thất bại ở tầng deconstruct Address.
5. **Inactive / low severity**: các record vẫn đầy đủ, nhưng guard false; đây không phải lỗi cấu trúc.
6. **Country hoặc city null**: `var country` và `var city` vẫn bind được null vì nested Address tồn tại; guard trả false theo điều kiện.
7. **City lowercase**: `"hcm"` khớp do dùng `equalsIgnoreCase`. Nếu code dùng `equals`, kết quả sẽ khác — điều cần review.
8. **Severity = 3**: xác nhận ngưỡng bao gồm giá trị 3.
9. **ID hoặc tên Customer null**: không ngăn nested pattern khớp do dùng `var` ở component trực tiếp. `PRIORITY:null` đến từ phép nối chuỗi; đây là hành vi mẫu, không phải khuyến nghị bỏ validation ID trong production.

`diagnose` ưu tiên báo **một lý do theo thứ tự kiểm tra**, không liệt kê toàn bộ nguyên nhân đồng thời. Ví dụ ticket inactive và country sai sẽ nhận `inactive`. Để liệt kê tất cả lý do, có thể xây một danh sách lỗi riêng, nhưng phải biết đây là hành vi khác với **short-circuit** của guard gốc.

## 7. Xây phương thức chẩn đoán mà không làm đổi ngữ nghĩa

Một cách debug thường gặp là chèn log vào giữa pattern hoặc thêm hàm có side effect vào `when`. Cách này có thể thay đổi thứ tự đánh giá, exception hoặc số lần gọi accessor. Với code production, nên ưu tiên:

1. **Giữ nguyên hàm phân loại đang chạy.**
2. **Đặt breakpoint** tại đầu nhánh `switch` hoặc tại caller để xem input và các component.
3. Tạo **hàm chẩn đoán thuần túy** (nếu có thể) nhận cùng input, phân tách các điều kiện với tên dễ hiểu.
4. Dùng cùng bộ dữ liệu test để chứng minh nhánh được chọn và lý do báo lỗi hợp lý.
5. Khi đã xác định nguyên nhân, chỉnh dữ liệu/logic theo yêu cầu rồi test hồi quy; không giữ instrumentation không cần thiết.

Ví dụ cách viết không an toàn:

```java
// Minh họa ý tưởng không nên lạm dụng:
if (input instanceof Ticket ticket && logAndCheck(ticket)) {
    // ...
}
```

Nếu `logAndCheck` ghi log, tăng metric, gọi network hoặc ném lỗi, đường đi runtime có thể thay đổi. Khi gắn trace cho một hệ thống thực, nên kiểm soát side effect và chỉ thu thập thông tin cần thiết; tránh in thông tin cá nhân hoặc token/bí mật từ các component.

Nếu accessor record được khai báo tường minh (không phải accessor mặc định) và có side effect, thậm chí việc đọc lại component nhiều lần để chẩn đoán cũng có thể gây khác biệt. Với record dữ liệu thông thường không tùy biến accessor, phương pháp tách từng check như `diagnose` rất hữu ích.

## 8. Thứ tự case: code chạy nhưng nhánh không được chọn

Trong `switch`, JVM xét case labels theo thứ tự khai báo, chỉ chọn nhánh phù hợp đầu tiên có guard đạt yêu cầu.

Phiên bản hợp lệ:

```java
return switch (input) {
    case null -> "ROOT_NULL";
    case Ticket(var id,
                Customer(var name, Address(var city, var country)),
                var severity, var active)
            when active && severity >= 3
                 && "VN".equals(country)
                 && city != null
                 && city.equalsIgnoreCase("HCM")
            -> "PRIORITY:" + id;
    case Ticket ticket -> "STANDARD:" + ticket.id();
    default -> "OTHER_TYPE";
};
```

Đặt nhánh Ticket có guard **trước** nhánh Ticket tổng quát là quan trọng. Nếu đảo lại:

```java
case Ticket ticket -> "STANDARD";
case Ticket(var id, var customer, var severity, var active)
        when active -> "PRIORITY";
```

đây **không phải lỗi runtime “pattern không match”**. Với Java 21, nhánh guarded thứ hai bị bao phủ bởi `case Ticket ticket` trước đó (*dominated case label*), nên compiler từ chối. Cần phân biệt thông báo compile-time dominance với tình huống code biên dịch nhưng guard false.

Thứ tự cũng quan trọng khi có **nhiều guard cùng đúng** mà không bị dominance về mặt kiểu: nhánh đầu tiên được chọn. Khi debug, hãy đọc toàn bộ `switch` thay vì chỉ một `case` bị nghi ngờ.

## 9. Lỗi compile time khác lỗi no-match runtime

Một số hiện tượng trông giống “pattern không match” nhưng chương trình còn chưa được biên dịch:

| Triệu chứng | Nhóm lỗi | Cách xử lý |
|---|---|---|
| Compiler báo kiểu không tương thích giữa selector và pattern | **Applicability tại compile time** | Xem kiểu tĩnh của selector và tính hợp lệ của checked cast |
| Compiler báo sai số component ở record pattern | **Cú pháp/arity** | Đối chiếu record components và thứ tự khai báo |
| Compiler báo dominated case label | **Thứ tự/sự bao phủ case** | Đặt case hẹp hoặc guarded trước case rộng |
| Compiler báo switch expression không exhaustive | **Tập case chưa đủ** | Thêm case thiếu theo domain, không tùy tiện thêm default để che lỗi |
| Code chạy, `instanceof` trả false | **Runtime no-match** | Kiểm tra root type/null và từng nested pattern |
| Code chạy, chọn fallback Ticket | **Pattern/guard cụ thể không đạt** | Tách kiểm tra cấu trúc và guard nghiệp vụ |
| Code ném NullPointerException trong guard | **Dereference không an toàn** | Xem leaf null, thứ tự `&&`/`||` và accessor |
| Code ném NullPointerException khi switch selector null | **Null selector chưa xử lý** | Thêm `case null` hoặc validate non-null ở boundary |

**Kiểu tĩnh khác kiểu runtime:** `Object value = new Ticket(...)` có thể được kiểm tra bằng `value instanceof Ticket t`. Nhưng nếu một loại pattern không applicable với **kiểu tĩnh** của biểu thức, compiler từ chối ngay; không có runtime match để phân tích. Khi gặp thông báo `javac`, hãy giải quyết nó trước khi viết test runtime.

## 10. Ngộ nhận phổ biến khi debug

### 10.1. “Root đúng kiểu thì record pattern sâu phải match”

Không đúng. Root Ticket có thể tồn tại nhưng Customer/Address null. Nested record pattern không khớp ở tầng null đó, trước khi xét guard.

### 10.2. “Component String null làm record pattern luôn thất bại”

Không đúng trong các ví dụ `var` của Java 21: `var city` trực tiếp trên component String có thể bind null. Điều kiện `city != null` trong guard mới là chốt chặn.

### 10.3. “Nếu đặt println ở cuối guard mà không thấy log thì pattern không match”

Không chắc. `&&` có short-circuit: điều kiện phía trước false khiến biểu thức sau không được đánh giá; hoặc pattern cấu trúc đã không khớp. Không có log ở cuối **không chứng minh** không vào guard.

### 10.4. “Thêm default sẽ giúp biết nguyên nhân”

`default` chỉ xử lý phần còn lại theo thiết kế, không tự cung cấp nguyên nhân. Với sealed/enum domain đóng, thêm `default` bừa bãi còn có thể che mất exhaustiveness khi xuất hiện biến thể mới. Với Object đầu vào mở, default là fallback bình thường nhưng cần log/chẩn đoán riêng nếu muốn chi tiết.

### 10.5. “Chuyển String thành chữ thường rồi so sánh là tương đương”

Không nhất thiết. `equalsIgnoreCase`, `toLowerCase` và `trim`/`strip` có ngữ nghĩa và phạm vi Unicode/locale khác nhau. Phải xác định chính sách chuẩn hóa của domain, không tự thay biểu thức chỉ vì giá trị cụ thể không match.

### 10.6. “Chỉ cần test một input thành công”

Một test thành công không phân biệt được root null, nested null, guard false, sai ngưỡng hoặc sai tên nhóm. Bộ test nên có một đại diện cho mỗi cổng từ chối.

### 10.7. “Nhìn thấy biến sau instanceof thì ở đâu cũng dùng được”

Không đúng. Pattern variables có phạm vi xác định bởi **flow scoping**. Với `input instanceof Ticket ticket && ticket.active()`, `ticket` có scope hợp lệ ở vế phải của `&&` vì vế trái phải khớp trước. Nhưng không thể tùy tiện dùng nó ở nhánh nơi pattern có thể đã thất bại.

### 10.8. “No-match là lỗi Java thay vì lỗi dữ liệu”

Rất nhiều trường hợp no-match là hành vi mong đợi của pattern. Hãy so sánh với contract: nếu một Ticket inactive phải đi vào STANDARD, việc không chọn PRIORITY là **đúng**. Bug chỉ tồn tại khi kết quả khác chính sách dự kiến.

## 11. Kiểm thử chẩn đoán: kỳ vọng độc lập và ma trận biên

Chương trình mục 6 cố ý nhận cả `expectedRoute`, `expectedReason` và `expectedPriority`. Điều này giúp tránh lỗi kiểm thử chỉ viết:

```java
assert route(input).startsWith("PRIORITY") == isPriority(input);
```

Nếu cả hai hàm cùng có một bug phân loại, chúng vẫn có thể bằng nhau. Expected độc lập từ chính sách giúp test mạnh hơn.

Khi chuyển thành JUnit 5, có thể dùng parameterized tests với các cột:

| Tình huống | Kỳ vọng match cấu trúc sâu? | Kỳ vọng guard? | Kỳ vọng route |
|---|---|---|---|
| Root null | Không | Không đánh giá | ROOT_NULL |
| Sai kiểu | Không | Không đánh giá | OTHER_TYPE |
| Customer null | Không | Không đánh giá | STANDARD |
| Address null | Không | Không đánh giá | STANDARD |
| Country null | Có | False | STANDARD |
| City null | Có | False | STANDARD |
| Inactive | Có | False | STANDARD |
| Severity = 2 | Có | False | STANDARD |
| City = `hcm`, severity = 4 | Có | True | PRIORITY |
| Severity = 3 | Có | True | PRIORITY |
| ID null, component còn lại hợp lệ | Có | True | PRIORITY:null |

**Không cần dựng framework để xác minh một lỗi nhỏ:** chạy chương trình Java tự chứa là đủ để kiểm tra một giả thuyết. Nhưng trong repository thật, test nên nằm cạnh domain code và được đưa vào CI. Đừng sử dụng diagnostic helper production như một bản sao không kiểm soát của policy: nếu rule thay đổi, hai nơi có thể lệch; cần làm rõ chủ sở hữu của điều kiện.

## 12. Quy trình debug thực tế theo từng bước

Khi một pattern mà bạn mong đợi lại không match:

1. **Đọc thông báo build trước.** Nếu javac không biên dịch, đây là lỗi applicability, scope, dominance hoặc exhaustiveness, chưa phải hành vi runtime.
2. **Xác định selector và kiểu tĩnh.** Đối chiếu khai báo `Object`/interface/generic với kiểu pattern. Dùng debugger kiểm tra giá trị runtime và null; tránh suy đoán từ log `toString`.
3. **Kiểm tra null tại root.** Nếu root null, `instanceof` false; với `switch` xem đã có `case null` hay chưa.
4. **Kiểm tra root type.** Nếu sai kiểu, không xét nested record/guard.
5. **Duyệt từng nested record theo thứ tự.** Customer null? Address null? Một tầng null đủ làm deep pattern fail.
6. **Ghi lại các component lá được bind.** ID, name, city, country có thể null dù pattern sâu đã match.
7. **Kiểm tra guard độc lập.** Với `&&`, ghi giá trị điều kiện con (nếu an toàn), xem điều kiện false đầu tiên và nhóm ngoặc. Giữ thứ tự short-circuit.
8. **Đọc các case phía trên.** Nếu code đã biên dịch, xem có guard khác bắt input trước không; nếu bị dominance, javac đã báo từ trước.
9. **Xác minh fallback.** Sau khi nhánh ưu tiên không match, input rơi vào Ticket fallback hay default? Thiếu fallback có thể làm đổi output khi refactor.
10. **Viết test với expected độc lập** cho input gây lỗi và một trường hợp thành công tương ứng.
11. **Kiểm tra exception/side effect.** Một accessor hay guard có thể ném exception, không nên ghi nhận nhầm thành boolean false.
12. **Sửa đúng tầng gây lỗi**, rồi chạy regression tests trước khi kết luận vấn đề được giải quyết.

Mục tiêu của quy trình này là trả lời câu cụ thể: **“Tại cổng nào input bị loại, theo quy tắc nào, và điều đó có đúng contract không?”**

## 13. Bài tập tự kiểm tra

Xét:

```java
record Location(String zone) {}
record User(String name, Location location) {}
Object value = new User("Lan", new Location(null));
```

**Bài 1:** `value instanceof User(var name, Location(var zone))` có khớp không?  
**Đáp án:** Có. Root User và nested Location khác null, còn `var zone` có thể bind null.

**Bài 2:** Thêm `&& zone.startsWith("A")` thì có an toàn không?  
**Đáp án:** Không. Pattern đã khớp nhưng `zone` có thể null, khiến `startsWith` ném NPE. Cần `&& zone != null && zone.startsWith("A")`.

**Bài 3:** Thay value bằng `new User("Lan", null)` thì deep pattern có khớp không?  
**Đáp án:** Không. `Location(...)` là nested record pattern, không khớp null.

**Bài 4:** Thay deep pattern bằng `User(var name, var location)`, trường hợp location null có khớp không?  
**Đáp án:** Có. `var location` bind trực tiếp giá trị null của component.

**Bài 5:** Nếu selector `null`, có thể dùng `instanceof User u` để lấy `u` không?  
**Đáp án:** Không; `instanceof` false và `u` không được bind.

**Bài 6:** Nếu một guarded `case` không được chọn nhưng `case User u` vẫn được chọn, điều gì có thể đã xảy ra?  
**Đáp án:** Guard false hoặc pattern chi tiết hơn không match, trong khi type pattern User rộng hơn khớp. Cần kiểm tra cả cấu trúc và guard.

**Bài 7:** Khi `city` bằng `" HCM "`, so sánh `city.equalsIgnoreCase("HCM")` có đúng không?  
**Đáp án:** False, vì phương thức bỏ qua khác biệt chữ hoa/thường chứ không tự loại khoảng trắng.

## Kết luận

Phân tích **vì sao pattern không match** đòi hỏi đi qua đúng các tầng: **compile time → kiểu/null ở root → cấu trúc record lồng nhau → component lá → guard → thứ tự case/fallback**. Hai tình huống `false` của `instanceof` có thể xuất phát từ nguyên nhân hoàn toàn khác nhau; còn một nhánh `switch` không chạy không có nghĩa là pattern cấu trúc đã thất bại, vì guard có thể trả false.

Trong Java 21, **nested record null** làm pattern sâu không khớp, trong khi **component lá null** có thể vẫn được bind. Tách các điều kiện chẩn đoán thành phương thức có tên, bổ sung expected test cho từng nguyên nhân và bảo vệ `&&`/`||` khỏi NPE là cách hiệu quả để tìm lỗi mà không làm che khuất semantics của pattern matching.

## Tài liệu tham khảo

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JLS Java SE 21 — Patterns §14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [JLS Java SE 21 — instanceof §15.20.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2)
- [JLS Java SE 21 — Switch Statements §14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
