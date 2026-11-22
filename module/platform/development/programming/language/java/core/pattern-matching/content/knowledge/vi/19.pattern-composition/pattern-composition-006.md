# Kết hợp nhiều nhánh type hierarchy trong Java Pattern Matching

## 1. Vì sao cần kết hợp nhiều nhánh của type hierarchy?

Trong ứng dụng Java, một kiểu cha thường có nhiều nhóm con. Ví dụ một hệ thống ghi nhận hoạt động có hai nhánh lớn:

- **AccountAction**: thao tác tài khoản, gồm `Login` và `Logout`.
- **ServiceSignal**: tín hiệu dịch vụ, gồm `Ping` và `Fault`.

Cả hai đều thuộc kiểu cha `Activity`. Nếu xử lý bằng nhiều phép `instanceof`, ép kiểu và các nhánh `if/else` lồng nhau, ta dễ làm rối phần điều hướng kiểu với logic xử lý từng biến thể.

**Pattern matching** cho phép diễn đạt các nhánh kiểu bằng `case`, đồng thời kết hợp **type pattern**, **record pattern lồng nhau** và điều kiện `when` ngay tại nơi lựa chọn xử lý.

Mục tiêu của bài học:
1. Thiết kế và đọc một **sealed type hierarchy nhiều cấp, nhiều nhánh**.
2. Phân biệt khớp một **nhánh lớn** (`AccountAction`, `ServiceSignal`) với khớp một **kiểu lá** (`Login`, `Logout`, `Ping`, `Fault`).
3. Kết hợp các record pattern, type pattern và guard trong cùng một `switch`.
4. Hiểu thứ tự `case`, dominance, exhaustiveness, `null` và cách bảo trì khi hierarchy thay đổi.
5. Biết khi nào dùng `default`, khi nào dùng một pattern cho cả nhánh và khi nào nên tách xử lý ra phương thức riêng.

**Phiên bản Java:** Pattern matching cho `switch` (JEP 441) và record patterns (JEP 440) là tính năng chính thức trong **Java 21**. Ví dụ hoàn chỉnh bên dưới dùng Java 21, không cần `--enable-preview`. `instanceof` với type pattern đã chính thức từ Java 16.

## 2. Thiết kế hierarchy với hai nhánh chính

Xem cấu trúc kiểu sau:

```text
Activity (sealed interface)
├── AccountAction (sealed interface)
│   ├── Login (record)
│   └── Logout (record)
└── ServiceSignal (sealed interface)
    ├── Ping (record)
    └── Fault (record)
```

Tương ứng với khai báo Java:

```java
sealed interface Activity permits AccountAction, ServiceSignal {}

sealed interface AccountAction extends Activity
        permits Login, Logout {}

sealed interface ServiceSignal extends Activity
        permits Ping, Fault {}

record Place(String city, String country) {}

record Login(String user, Place place) implements AccountAction {}

record Logout(String user) implements AccountAction {}

record Ping(String service, int latencyMs) implements ServiceSignal {}

record Fault(String service, int status) implements ServiceSignal {}
```

Các dòng trên là **đoạn minh họa khai báo**; trong chương trình đầy đủ ở phần 4, chúng được đặt bên trong một class.

`sealed` và `permits` giúp khai báo tập subtype trực tiếp được phép mở rộng một kiểu. Ở đây `Activity` có đúng hai nhánh trực tiếp; mỗi nhánh lại liệt kê các record lá. Record vốn `final`, nên không có subtype mới của từng record. Mỗi subtype trực tiếp của một kiểu `sealed` phải phù hợp với quy tắc `final`, `sealed` hoặc `non-sealed`; với interface con trong ví dụ, ta chọn `sealed` để tiếp tục kiểm soát cây kiểu.

Điểm quan trọng: **thứ tự xét kiểu là quan hệ cha–con**, còn **thứ tự xét guard là điều kiện bên trong từng nhánh kiểu**. Hai cơ chế này phối hợp nhưng không thay thế nhau.

### Khớp nhánh lớn bằng type pattern

Khi chỉ cần biết hoạt động thuộc nhóm nào, ta có thể kiểm tra ở cấp interface:

```java
// Đoạn minh họa trong một phương thức có tham số Activity activity:
if (activity instanceof AccountAction) {
    System.out.println("ACCOUNT");
} else if (activity instanceof ServiceSignal) {
    System.out.println("SERVICE");
} else {
    System.out.println("NONE");
}
```

Với một object `Login` hoặc `Logout`, phép kiểm tra `instanceof AccountAction` đều đúng. Tương tự, `Ping` và `Fault` đều thuộc `ServiceSignal`. `null` không khớp bất kỳ phép `instanceof` nào.

Khi cần dùng lại biến theo kiểu interface, ta có thể dùng **type pattern**: `activity instanceof AccountAction action`. Biến `action` được ràng buộc và dùng trong nhánh đã khớp.

### Khớp các kiểu lá bằng record pattern

Khi cần đọc dữ liệu của từng subtype, thay vì chỉ kiểm tra nhóm, `switch` có thể có các case như:

```java
case Logout(String user) -> "LOGOUT " + user;
case Ping(String service, int latencyMs) -> "PING " + service;
```

Đây là **những nhánh minh họa** của một `switch` expression, không phải chương trình độc lập. Pattern vừa nhận dạng record `Logout`/`Ping`, vừa ràng buộc component để xử lý.

## 3. Ba cấp phối hợp pattern trong cùng một switch

Với `Login(String user, Place place)`, có thể kết hợp:

```java
case Login(String user, Place(String city, String country))
        when "VN".equals(country) ->
    "LOGIN_VN " + user + "@" + city;
```

Hãy đọc nhánh này theo thứ tự:

1. **Nhánh hierarchy:** Selector phải là kiểu lá `Login` thuộc nhánh `AccountAction`.
2. **Record pattern ngoài:** `Login(...)` bóc tách hai component `user` và `place`.
3. **Record pattern trong:** `Place(String city, String country)` yêu cầu `place` là một `Place` khác `null` và bóc tách hai component của `Place`.
4. **Type patterns:** `String user`, `String city`, `String country` ràng buộc giá trị theo kiểu component.
5. **Guard:** `when "VN".equals(country)` chỉ đúng với country có giá trị `"VN"`, không gây `NullPointerException` khi country bằng `null` vì gọi `equals` trên hằng chuỗi.

Nếu guard sai, Java có thể tiếp tục xét case kế tiếp. Nếu `place` là `null` thì nested `Place(...)` không khớp; ta cần một fallback riêng cho `Login` nếu muốn xử lý trường hợp đó.

Viết mỗi biến thể thành một case dễ theo dõi hơn một chuỗi ép kiểu như `((Login) activity).place().city()`. Tuy nhiên, pattern matching vẫn là cơ chế đọc và kiểm tra dữ liệu; nó không biến cấu trúc object thành immutable sâu, không tự tạo bản sao và không tự xác thực quy tắc nghiệp vụ.

## 4. Ví dụ hoàn chỉnh chạy được trên Java 21

Tạo file **`HierarchyPatternDemo.java`**:

```java
public class HierarchyPatternDemo {
    sealed interface Activity permits AccountAction, ServiceSignal {}

    sealed interface AccountAction extends Activity
            permits Login, Logout {}

    sealed interface ServiceSignal extends Activity
            permits Ping, Fault {}

    record Place(String city, String country) {}

    record Login(String user, Place place) implements AccountAction {}

    record Logout(String user) implements AccountAction {}

    record Ping(String service, int latencyMs) implements ServiceSignal {}

    record Fault(String service, int status) implements ServiceSignal {}

    static String group(Activity activity) {
        if (activity instanceof AccountAction) {
            return "ACCOUNT";
        }
        if (activity instanceof ServiceSignal) {
            return "SERVICE";
        }
        return "NONE";
    }

    static String describe(Activity activity) {
        return switch (activity) {
            case Login(String user, Place(String city, String country))
                    when "VN".equals(country) ->
                "LOGIN_VN " + user + "@" + city;

            case Login(String user, Place(String city, String country)) ->
                "LOGIN " + user + "@" + city + "," + country;

            case Login(var user, var place) ->
                "LOGIN_UNKNOWN_PLACE " + user;

            case Logout(String user) ->
                "LOGOUT " + user;

            case Ping(String service, int latencyMs)
                    when latencyMs < 0 ->
                "PING_INVALID " + service;

            case Ping(String service, int latencyMs)
                    when latencyMs > 100 ->
                "PING_SLOW " + service + "=" + latencyMs + "ms";

            case Ping(String service, int latencyMs) ->
                "PING_OK " + service + "=" + latencyMs + "ms";

            case Fault(String service, int status)
                    when status >= 500 ->
                "FAULT_CRITICAL " + service + "=" + status;

            case Fault(String service, int status) ->
                "FAULT " + service + "=" + status;

            case null -> "NO_EVENT";
        };
    }

    public static void main(String[] args) {
        Activity[] values = {
            new Login("An", new Place("HaNoi", "VN")),
            new Login("Binh", new Place("Paris", "FR")),
            new Login("Chi", null),
            new Logout("Dung"),
            new Ping("search", 45),
            new Ping("api", 125),
            new Ping("queue", -1),
            new Fault("billing", 503),
            new Fault("auth", 401),
            null
        };

        for (Activity value : values) {
            System.out.println(group(value) + " | " + describe(value));
        }
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac --release 21 HierarchyPatternDemo.java
java HierarchyPatternDemo
```

Kết quả chuẩn:

```text
ACCOUNT | LOGIN_VN An@HaNoi
ACCOUNT | LOGIN Binh@Paris,FR
ACCOUNT | LOGIN_UNKNOWN_PLACE Chi
ACCOUNT | LOGOUT Dung
SERVICE | PING_OK search=45ms
SERVICE | PING_SLOW api=125ms
SERVICE | PING_INVALID queue
SERVICE | FAULT_CRITICAL billing=503
SERVICE | FAULT auth=401
NONE | NO_EVENT
```

Giải thích các trường hợp:

| Đầu vào | Nhánh xử lý | Lý do |
| --- | --- | --- |
| `Login("An", Place("HaNoi","VN"))` | `LOGIN_VN` | Nested record pattern khớp và guard country bằng `VN` |
| `Login("Binh", Place("Paris","FR"))` | `LOGIN` | Nested pattern khớp nhưng guard `VN` sai |
| `Login("Chi", null)` | `LOGIN_UNKNOWN_PLACE` | Nested `Place(...)` không khớp null; fallback `Login(var ...)` nhận record |
| `Logout("Dung")` | `LOGOUT` | Kiểu lá khác trong nhánh `AccountAction` |
| `Ping("search",45)` | `PING_OK` | Hai guard không đúng, case `Ping` không guard xử lý |
| `Ping("api",125)` | `PING_SLOW` | `latencyMs > 100` |
| `Ping("queue",-1)` | `PING_INVALID` | `latencyMs < 0` |
| `Fault("billing",503)` | `FAULT_CRITICAL` | `status >= 500` |
| `Fault("auth",401)` | `FAULT` | Case `Fault` không guard |
| `null` | `NO_EVENT` | `case null` xử lý selector null |

Hàm `group` phân biệt **hai nhóm cha** của hierarchy. Hàm `describe` đi sâu vào **các kiểu lá** và kết hợp record patterns/guard. Tách hai trách nhiệm này cho thấy có thể xử lý ở mức trừu tượng phù hợp thay vì luôn đi tới từng kiểu lá.

Lưu ý: với ví dụ này, mã `switch` expression không chứa `default` vì tất cả các record lá trong hierarchy sealed đều được bao phủ bằng case không guard, bên cạnh `case null`. Điều này khác với `switch` trên `Object` hay hierarchy còn mở.

## 5. Exhaustiveness khi kết hợp nhiều nhánh

Một `switch` expression phải **exhaustive**: tại thời điểm biên dịch, trình biên dịch cần chứng minh rằng mọi giá trị khác null thuộc kiểu selector đều có nhánh xử lý. Một hierarchy `sealed` giúp trình biên dịch biết danh sách các subtype hợp lệ.

Với ví dụ này:
- `Activity` chỉ cho phép trực tiếp `AccountAction` và `ServiceSignal`.
- `AccountAction` chỉ cho phép `Login`, `Logout`.
- `ServiceSignal` chỉ cho phép `Ping`, `Fault`.
- Các case không guard của `Login`, `Logout`, `Ping`, `Fault` bao phủ các kiểu lá tương ứng.
- `case null` làm rõ riêng trường hợp selector null.

Vì vậy ví dụ biên dịch được **không cần default**. Đây là lợi ích lớn của sealed hierarchy: nếu sửa source để thêm một subtype mới mà chưa xử lý nó, trình biên dịch có thể phát hiện một `switch` expression không còn exhaustive khi biên dịch lại.

### Guard không thay thế một case bao phủ

Case có `when` chỉ xử lý một phần tập giá trị của subtype:

```java
// Trích đoạn:
case Ping(String service, int latencyMs) when latencyMs > 100 ->
    "SLOW";
```

Chỉ case này **không đủ** để bao phủ mọi `Ping`. Cần thêm case không guard tương thích, ví dụ:

```java
// Trích đoạn tiếp theo:
case Ping(String service, int latencyMs) ->
    "OTHER";
```

Tương tự, `Login(String user, Place(...))` không nhận `Login` có `place == null`. Do đó ví dụ có `case Login(var user, var place)` làm fallback.

### Thay đổi khi hierarchy có nhánh non-sealed

Nếu một nhánh được khai báo `non-sealed`, các lớp khác có thể mở rộng nhánh ấy, nên một vài record lá đã biết **không còn là toàn bộ thế giới**. Có thể dùng một type pattern bao phủ nhánh, ví dụ `case ExtensionAction e -> ...`, hoặc một `default` phù hợp, thay vì chỉ liệt kê các subtype hiện có.

Khi selector khai báo kiểu `Object`, interface thông thường không sealed hoặc một lớp cha có subtype không đóng kín, **không được tự cho rằng** các case đã liệt kê là đủ. `default` hoặc một case type pattern phù hợp sẽ giúp switch expression xử lý hết kiểu còn lại.

### Chọn cấp độ khớp

Nếu chỉ cần thông tin chung của một nhóm, có thể dùng `case AccountAction action` hoặc `case ServiceSignal signal`. Nếu cần dữ liệu riêng của `Login` và `Logout`, hãy dùng các case kiểu lá. Không nhất thiết liệt kê mọi lá khi logic xử lý thực sự giống nhau.

Một type pattern nhánh cha được đặt trước các pattern con sẽ khiến những nhánh con sau không thể tới; vì thế cần chọn **cấp xử lý** và **thứ tự** có chủ ý.

## 6. Dominance và thứ tự case

Java kiểm tra **dominance**: case tổng quát không được xuất hiện trước case cụ thể mà nó bao phủ hoàn toàn.

Ví dụ sau **cố ý sai, không biên dịch** khi đặt trong cùng một `switch`:

```java
case AccountAction action -> "ACCOUNT";
case Login(String user, Place(var city, var country)) -> "LOGIN";
```

Mọi `Login` đều là `AccountAction`. Vì nhánh `AccountAction action` đã nhận subtype này, nhánh `Login(...)` phía sau không thể được chọn. Compiler báo lỗi dominated case.

Tương tự:

```java
// Cố ý sai nếu đặt theo thứ tự này:
case Ping(String service, int latencyMs) -> "PING";
case Ping(String service, int latencyMs) when latencyMs > 100 ->
    "SLOW_PING";
```

Nhánh `Ping` không guard bao phủ mọi `Ping`, làm nhánh `SLOW_PING` phía sau mất tác dụng. Đặt case có guard trước case tổng quát.

**Quy tắc thực hành:** Xếp từ điều kiện cụ thể tới tổng quát, rồi đến fallback. Các sibling trong hai nhánh không có quan hệ kế thừa (chẳng hạn `Login` và `Fault`) không tự bao phủ nhau; thứ tự tương đối của chúng thường là lựa chọn trình bày, không quyết định kết quả matching.

## 7. Null và phạm vi biến pattern

### Null ở đầu vào

`switch` trên một tham chiếu `null` cần xử lý tường minh bằng `case null` nếu muốn trả kết quả thay vì gặp `NullPointerException`. `default` thông thường không tự bắt selector null. Với `instanceof`, biểu thức trên null trả `false`.

### Null ở record lồng nhau

Record `Login("Chi", null)` là một object `Login` hợp lệ theo định nghĩa record hiện tại, nhưng component `place` là null. Nó không khớp `Place(String city, String country)`, bởi một **record pattern** yêu cầu đối tượng con khác null.

Tuy vậy `Login(var user, var place)` vẫn khớp: `var place` là pattern unconditional đối với component kiểu `Place` nên có thể ràng buộc giá trị null. Vì vậy một fallback dạng `var` cần kiểm tra null riêng nếu chuẩn dữ liệu không cho phép.

Một type pattern đặt tại component có kiểu chính xác tương ứng cũng có thể unconditional trong record pattern. Không áp dụng quy tắc này một cách máy móc cho mọi type pattern ở một vị trí kiểu rộng hơn; ví dụ `String text` tại component khai báo `Object` không khớp `null`.

### Phạm vi

Các biến `user`, `city`, `country` được ràng buộc bởi record pattern chỉ dùng được ở guard `when` và phần thân của case tương ứng; chúng không tự tồn tại ở case khác hoặc sau `switch`. Trong `instanceof` kết hợp `&&`, chúng chỉ dùng được tại những vị trí Java xác nhận nhánh đã khớp.

Đặt tên biến khác nhau nếu nhiều component cùng có ý nghĩa tương tự, ví dụ `sourceService` và `targetService`. Tránh khai báo trùng tên trong cùng pattern hoặc tham chiếu biến từ case không khớp.

## 8. Các lỗi thường gặp khi phối hợp nhánh hierarchy

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Case cha trước case lá | Case lá bị dominated | Đưa case lá cần xử lý riêng lên trước |
| Chỉ dùng case có `when` cho một subtype | Không bao phủ hết subtype | Thêm case không guard hoặc fallback phù hợp |
| Giả định record con không thể null | Một số nested patterns bỏ qua record dù record ngoài hợp lệ | Dùng case fallback và quy tắc dữ liệu rõ ràng |
| Dùng `default` thay cho `case null` | `switch` có thể ném `NullPointerException` khi selector null | Xử lý null tường minh nếu đầu vào có thể null |
| Bỏ `default` cho một hierarchy mở | Switch expression có thể không exhaustive | Dùng case bao phủ nhánh mở hoặc `default` |
| Gộp mọi logic vào một case rất dài | Pattern khó đọc, guard nhiều điều kiện | Tách hàm xử lý theo nhóm hoặc subtype |
| Thêm subtype mà không kiểm tra lại switch | Các nhánh cần cập nhật; biên dịch lại có thể phát hiện thiếu coverage | Chạy biên dịch và kiểm thử sau thay đổi hierarchy |
| Dùng record pattern trên class không phải record | Lỗi cú pháp/kiểu | Dùng type pattern và phương thức của class thường |

**Không nhầm pattern matching với đa hình (polymorphism) thông thường:** Nếu hành vi chủ yếu thuộc về từng object và có thể diễn đạt tốt bằng phương thức chung của interface, dispatch động qua method vẫn phù hợp. Pattern matching hữu ích khi bên tiêu thụ cần tổng hợp hoặc chuyển đổi nhiều dạng dữ liệu, chẳng hạn hiển thị, ánh xạ DTO, xuất log hay xử lý một protocol có các biến thể đóng kín.

**Không mặc định pattern matching nhanh hơn chuỗi accessor/cast.** Mục tiêu chính là biểu đạt cấu trúc và kiểm tra bao phủ nhánh. Khi hiệu năng thực sự là yêu cầu, đo trên luồng xử lý của ứng dụng.

## 9. Quy trình triển khai và bài tập

Khi thêm xử lý nhiều nhánh:
1. Vẽ cây kiểu, xác định nhánh nào `sealed` và nhánh nào còn mở.
2. Xác định logic nào áp dụng cho cả nhánh lớn, logic nào chỉ áp dụng cho subtype lá.
3. Dùng type pattern tại cấp cha khi xử lý chung; dùng record pattern tại subtype khi cần component.
4. Với nested record pattern, kiểm tra rõ trường hợp component null.
5. Đặt các guard `when` trước case không guard của cùng subtype.
6. Đảm bảo switch expression bao phủ mọi subtype và xử lý selector null theo nhu cầu.
7. Kiểm tra đầu vào ở từng nhánh, giá trị biên guard, null, subtype mới và các case fallback.

### Bài tập 1: Thêm một kiểu lá

Bổ sung `record PasswordReset(String user) implements AccountAction {}` và thêm `PasswordReset` vào `permits` của `AccountAction`. Sau khi khai báo, thử biên dịch lại `describe`: quan sát lỗi do switch expression thiếu coverage nếu chưa có case mới. Thêm case `PasswordReset(String user) -> "PASSWORD_RESET " + user;` trước khi biên dịch lại.

Bài tập cho thấy sealed hierarchy giúp phát hiện một nhánh mới chưa được xử lý.

### Bài tập 2: Thêm guard cho một nhánh

Thêm case `Fault` dành riêng cho `status == 429`, trả về thông điệp `"FAULT_THROTTLED <service>"`. Đặt case này **trước** case `Fault` không guard, đồng thời cân nhắc vị trí tương đối với guard `status >= 500`. Thử `429`, `500` và `400`: mỗi giá trị phải được điều hướng tới đúng case.

### Bài tập 3: Chọn mức trừu tượng

Giả sử muốn thống kê số lần xuất hiện của `AccountAction` và `ServiceSignal` mà không quan tâm subtype. Hãy so sánh hai hướng: dùng hai type pattern ở cấp interface, hoặc liệt kê bốn record pattern ở cấp lá. Chọn cách ít lặp hơn cho yêu cầu thống kê; chỉ dùng pattern cụ thể khi thực sự cần dữ liệu riêng.

**Ghi nhớ:** Kết hợp nhiều nhánh type hierarchy hiệu quả khi tách rõ **kiểu cha dùng để nhóm**, **kiểu lá dùng để xử lý dữ liệu** và **guard dùng để lọc giá trị**. Với cây `sealed` đóng kín, Java 21 có thể kiểm tra exhaustive khi biên dịch. Viết case cụ thể trước case tổng quát và luôn cân nhắc null, fallback cùng khả năng mở rộng hierarchy.

## Tài liệu tham khảo

- Java Language Specification, Java SE 21 — Pattern Matching: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11
- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java SE 21 — Sealed Classes and Interfaces: https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
