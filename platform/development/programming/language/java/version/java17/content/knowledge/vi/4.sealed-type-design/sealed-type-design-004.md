# Ảnh hưởng của `non-sealed` đến ranh giới mở rộng trong Java 17

Trong Java 17, `sealed` cho phép người thiết kế **giới hạn những kiểu nào được trực tiếp kế thừa một class hoặc mở rộng/triển khai một interface**. Tuy nhiên, một hệ thống đôi khi cần giữ lõi nghiệp vụ có kiểm soát, đồng thời cho phép ứng dụng hoặc đối tác bổ sung kiểu mới. Từ khóa `non-sealed` giải quyết nhu cầu đó bằng cách **mở lại quyền mở rộng tại một nhánh cụ thể của cây kiểu**.

Bài học này phân tích `non-sealed` làm thay đổi ranh giới mở rộng như thế nào, vì sao một kiểu cha vẫn có thể là `sealed` khi một nhánh con của nó là `non-sealed`, và cách thiết kế API để duy trì hợp đồng hành vi khi có những kiểu con chưa biết trước.

> **Bối cảnh phiên bản:** Sealed classes/interfaces và `non-sealed` là tính năng chính thức của **Java 17** (JEP 409). Các ví dụ bên dưới dùng cú pháp chuẩn của Java 17, không cần bật tính năng preview.

## 1. Ranh giới mở rộng là gì?

Giả sử hệ thống có một interface `PaymentMethod`. Nếu khai báo interface thông thường:

```java
interface PaymentMethod {
    void pay();
}
```

Mọi class có quyền truy cập interface này đều có thể `implements PaymentMethod`. Đây là một **ranh giới mở**: người thiết kế không kiểm soát tập hợp các kiểu trực tiếp triển khai `PaymentMethod`.

Nếu thay bằng `sealed interface`:

```java
sealed interface PaymentMethod permits CashPayment, OnlinePayment {
    void pay();
}
```

thì chỉ các kiểu **được liệt kê trực tiếp trong `permits`** mới có thể trực tiếp triển khai hoặc mở rộng `PaymentMethod`:

- `CashPayment`
- `OnlinePayment`

Một kiểu khác khai báo `implements PaymentMethod` trực tiếp sẽ bị từ chối nếu không thuộc danh sách trên. Ranh giới này được kiểm tra ở mức ngôn ngữ và JVM, không đơn thuần là quy ước đặt tên.

Điểm cần phân biệt: `sealed` kiểm soát **tập con trực tiếp**, chứ không nhất thiết cố định mọi kiểu ở các tầng sâu hơn của toàn bộ cây kế thừa. Quyền mở rộng của từng nhánh phụ thuộc vào cách nhánh đó được khai báo.

## 2. Ba lựa chọn của một kiểu con trực tiếp

Một kiểu trực tiếp kế thừa hoặc triển khai kiểu `sealed` phải thể hiện cách nó xử lý quyền mở rộng tiếp theo:

| Khai báo tại nhánh con | Ý nghĩa | Khả năng tạo kiểu con tiếp theo |
| --- | --- | --- |
| `final class` | Đóng hoàn toàn nhánh class tại đây. | Không class nào được `extends` class này. |
| `sealed class` / `sealed interface` | Tiếp tục giới hạn các kiểu con trực tiếp. | Chỉ những kiểu thuộc `permits` của chính nhánh đó. |
| `non-sealed class` / `non-sealed interface` | Gỡ giới hạn sealed đối với việc mở rộng nhánh này. | Các kiểu có quyền truy cập được phép `extends`/`implements` theo quy tắc Java thông thường. |

Với `final`, không thể khai báo `final interface`; một interface con của `sealed interface` thường chọn `sealed` hoặc `non-sealed`. Một `record` trực tiếp triển khai `sealed interface` cũng hợp lệ vì bản thân record là `final` theo ngữ nghĩa của Java.

Ví dụ:

```java
sealed interface Notification
        permits EmailNotification, SmsNotification, CustomNotification {
}

final class EmailNotification implements Notification {
}

sealed class SmsNotification implements Notification
        permits TransactionalSms {
}

final class TransactionalSms extends SmsNotification {
}

non-sealed interface CustomNotification extends Notification {
}
```

Trong hệ thống này:

- Nhánh `EmailNotification` dừng lại ngay tại class `final`.
- Nhánh `SmsNotification` chỉ cho phép `TransactionalSms` trực tiếp mở rộng.
- Nhánh `CustomNotification` có thể nhận thêm các implementation khác mà không cần thêm chúng vào `Notification.permits`.

Sự kết hợp này giúp giới hạn phần nghiệp vụ lõi và dành ra một điểm mở rộng được thiết kế có chủ đích.

## 3. `non-sealed` mở nhánh nào, và không mở nhánh nào?

Xét cây kiểu sau:

```text
Notification  (sealed)
│
├── EmailNotification  (final)
│
├── SmsNotification  (sealed)
│   └── TransactionalSms  (final)
│
└── CustomNotification  (non-sealed interface)
    ├── AppPushNotification
    ├── PartnerNotification
    └── ... kiểu được bổ sung sau này
```

Khi `CustomNotification` là `non-sealed`, **chỉ nhánh bên dưới `CustomNotification` được mở rộng theo quy tắc thông thường**. Từ khóa đó không tự động biến `Notification` thành một interface mở.

Chẳng hạn, khai báo sau hợp lệ:

```java
class AppPushNotification implements CustomNotification {
}
```

Trong khi khai báo dưới đây không hợp lệ vì `Notification` vẫn là `sealed` và `UnknownNotification` không được phép là con trực tiếp:

```java
// Ví dụ cố ý KHÔNG biên dịch được
class UnknownNotification implements Notification {
}
```

Tức là người mở rộng phải đi qua **cửa mở đã định nghĩa** (`CustomNotification`) thay vì thêm bất kỳ loại con trực tiếp nào cho kiểu gốc.

### `non-sealed` không giới hạn các tầng bên dưới

Không chỉ implementation trực tiếp của `CustomNotification` được phép xuất hiện; các tầng kế thừa tiếp theo cũng được xử lý theo quy tắc thông thường:

```java
class PartnerNotification implements CustomNotification {
}

class PriorityPartnerNotification extends PartnerNotification {
}
```

`PriorityPartnerNotification` là một `Notification` **gián tiếp**; nó không cần xuất hiện trong `Notification.permits`. Nếu `PartnerNotification` được khai báo `final` thì việc mở rộng class đó sẽ bị chặn bởi `final`, nhưng đây là quyết định của class con, không phải giới hạn quay trở lại từ `Notification`.

Một kiểu ở dưới nhánh mở vẫn có thể chủ động `final` hoặc `sealed` để quản lý nhánh của chính nó. Vì vậy, “mở” không có nghĩa là mọi class hậu duệ đều bắt buộc phải mở.

## 4. Ví dụ chạy được trên Java 17: mở điểm tích hợp cho đối tác

Giả sử hệ thống giao hàng có lựa chọn giao tại quầy cố định và kênh tích hợp do đối tác cung cấp. Yêu cầu thiết kế:

1. Không ai được thêm loại giao hàng trực tiếp vào `DeliveryMethod` ngoài các nhánh do lõi công bố.
2. Đối tác có thể tạo lớp tích hợp mới mà không cần sửa `permits` của `DeliveryMethod`.
3. Mã lõi có thể xử lý mọi phương thức giao hàng thuộc nhánh tích hợp thông qua một hợp đồng chung.

Tạo tệp `NonSealedDemo.java`:

```java
public class NonSealedDemo {
    public static void main(String[] args) {
        printMethod(new CounterDelivery());
        printMethod(new PartnerDelivery());
        printMethod(new AnotherPartnerDelivery());
    }

    static void printMethod(DeliveryMethod method) {
        if (method instanceof CounterDelivery) {
            System.out.println("Nhận tại quầy");
        } else if (method instanceof ExtensionDelivery extension) {
            System.out.println("Tích hợp: " + extension.providerName());
        }
    }
}

sealed interface DeliveryMethod
        permits CounterDelivery, ExtensionDelivery {
}

final class CounterDelivery implements DeliveryMethod {
}

non-sealed interface ExtensionDelivery extends DeliveryMethod {
    String providerName();
}

final class PartnerDelivery implements ExtensionDelivery {
    @Override
    public String providerName() {
        return "Partner A";
    }
}

final class AnotherPartnerDelivery implements ExtensionDelivery {
    @Override
    public String providerName() {
        return "Partner B";
    }
}
```

Biên dịch và chạy:

```bash
javac NonSealedDemo.java
java NonSealedDemo
```

Kết quả:

```text
Nhận tại quầy
Tích hợp: Partner A
Tích hợp: Partner B
```

**Điểm quan trọng:** `PartnerDelivery` và `AnotherPartnerDelivery` không xuất hiện trong `DeliveryMethod.permits`. Chúng triển khai `ExtensionDelivery`, tức là tham gia **nhánh mở** mà API đã cho phép.

Lệnh `instanceof ExtensionDelivery extension` là **pattern matching cho `instanceof`**, đã là tính năng chuẩn trước Java 17. Nó vừa kiểm tra loại vừa cung cấp biến `extension` để gọi `providerName()`. Từ đó, mã xử lý không cần nêu đích danh từng đối tác.

### Vì sao điều này hữu ích cho API?

Với phương thức:

```java
static void printMethod(DeliveryMethod method)
```

API có thể tiếp tục dùng kiểu chung `DeliveryMethod` cho tham số. Các đối tác mới chỉ cần tuân thủ `ExtensionDelivery`. Lõi ứng dụng không cần thêm một nhánh `if` cho mỗi class đối tác, miễn là hành vi mong muốn được thể hiện bằng các phương thức trong hợp đồng `ExtensionDelivery`.

Ngược lại, nếu mã viết cố định từng class triển khai, ví dụ chỉ kiểm tra `PartnerDelivery`, nó sẽ bỏ sót `AnotherPartnerDelivery` và những kiểu được thêm sau này. `non-sealed` cho phép mở rộng cấu trúc kiểu, nhưng **không tự bảo đảm mã xử lý đã hỗ trợ mọi biến thể**.

## 5. `non-sealed class` và `non-sealed interface`: giống và khác

Nhánh mở có thể là class hoặc interface, nhưng quyền mở rộng thực tế tùy loại:

### Nhánh mở là class

```java
sealed abstract class AuditEvent
        permits SystemAuditEvent, UserAuditEvent {
}

final class SystemAuditEvent extends AuditEvent {
}

non-sealed class UserAuditEvent extends AuditEvent {
}

class LoginAuditEvent extends UserAuditEvent {
}

class FailedLoginAuditEvent extends LoginAuditEvent {
}
```

`UserAuditEvent` là `non-sealed class`: các class khác có thể `extends UserAuditEvent` nếu đáp ứng quy tắc truy cập và constructor thông thường. Các class `LoginAuditEvent` và `FailedLoginAuditEvent` không cần xuất hiện trong `AuditEvent.permits`.

Lưu ý: việc kế thừa một class vẫn chịu giới hạn **Java chỉ cho phép một superclass trực tiếp**, và constructor của superclass phải có cách gọi hợp lệ từ subclass.

### Nhánh mở là interface

```java
sealed interface ExportFormat permits BuiltInFormat, CustomFormat {
}

final class BuiltInFormat implements ExportFormat {
}

non-sealed interface CustomFormat extends ExportFormat {
    String fileExtension();
}

class CsvLikeFormat implements CustomFormat {
    @Override
    public String fileExtension() {
        return ".csv";
    }
}

interface ExtendedCustomFormat extends CustomFormat {
    String displayName();
}
```

`CustomFormat` là `non-sealed interface`, nên class có thể `implements`, còn interface khác có thể `extends` nó. Một class cũng có thể triển khai nhiều interface theo quy tắc bình thường. Tùy bài toán, interface thường phù hợp để công bố điểm mở rộng mà không ép người dùng kế thừa sẵn một class nền.

## 6. Các giới hạn ngôn ngữ vẫn phải tuân thủ

### 6.1. `non-sealed` chỉ dùng khi có quan hệ trực tiếp với kiểu `sealed`

Không thể gắn `non-sealed` tùy ý cho một class hoặc interface thông thường:

```java
// Không hợp lệ: Object không phải sealed class
non-sealed class FreeClass {
}
```

Một kiểu khai báo `non-sealed` phải là **kiểu con trực tiếp của ít nhất một kiểu `sealed`**. Ví dụ sau hợp lệ:

```java
sealed interface Command permits ExtendableCommand {
}

non-sealed interface ExtendableCommand extends Command {
}
```

Nhưng kiểu mở rộng tiếp theo không được tùy tiện viết `non-sealed` chỉ vì tổ tiên xa của nó là `sealed`:

```java
// Không hợp lệ: chỉ trực tiếp extends interface non-sealed
non-sealed interface ChildCommand extends ExtendableCommand {
}
```

Trong trường hợp này chỉ cần khai báo `interface ChildCommand extends ExtendableCommand`, hoặc chủ động dùng `sealed interface` cùng danh sách `permits` nếu muốn khép nhánh con.

### 6.2. Quy tắc `permits` áp dụng cho con trực tiếp

Các kiểu nằm trong danh sách `permits` của một kiểu `sealed` phải thực sự là **subclass/subinterface trực tiếp** của kiểu đó. Trong Java 17, kiểu con trực tiếp phải nằm trong **cùng named module** với kiểu `sealed`; nếu kiểu gốc thuộc **unnamed module**, chúng phải nằm trong **cùng package**. Việc khai báo `non-sealed` không bỏ qua những quy tắc này tại điểm nối trực tiếp với cha `sealed`.

Sau điểm nối đó, kiểu con của **nhánh `non-sealed`** không còn phải được liệt kê trong `permits` của tổ tiên. Với API công khai, nhánh mở có thể được triển khai từ module hoặc package khác nếu những điều kiện truy cập, phụ thuộc module và khả năng nhìn thấy kiểu cho phép.

### 6.3. `non-sealed` không thay thế các quy tắc truy cập

`non-sealed` không biến một kiểu `package-private` thành `public`, không làm constructor `private` thành truy cập được, không mở package bị ẩn bởi JPMS và không cho phép kế thừa class `final`.

Nếu một library muốn cho code ngoài module kế thừa nhánh mở, cần thiết kế mức truy cập thích hợp: chẳng hạn một `public non-sealed interface` nằm trong package được `exports` qua `module-info.java`. Khi dùng `non-sealed class`, các constructor truy cập được cũng cần đáp ứng nhu cầu subclass.

## 7. Thay đổi quan trọng trong tư duy thiết kế tập kiểu

Hãy phân biệt hai dạng giả định:

**Giả định A — Tập kiểu con trực tiếp của root được kiểm soát:**

```text
DeliveryMethod = CounterDelivery | ExtensionDelivery
```

Điều này đúng với khai báo `sealed DeliveryMethod` trong ví dụ. Người khác không thể trực tiếp thêm `NewDelivery implements DeliveryMethod` nếu `NewDelivery` không được cho phép.

**Giả định B — Tập mọi kiểu runtime của `DeliveryMethod` chỉ có hai class cụ thể:**

```text
DeliveryMethod = CounterDelivery | PartnerDelivery
```

Điều này **không đúng** khi nhánh `ExtensionDelivery` là `non-sealed`: `AnotherPartnerDelivery` hoặc vô số kiểu mới vẫn có thể là một `DeliveryMethod` hợp lệ thông qua nhánh mở.

| Khía cạnh thiết kế | Nhánh đóng bằng `final` hoặc được kiểm soát tiếp bằng `sealed` | Nhánh mở bằng `non-sealed` |
| --- | --- | --- |
| Tập kiểu có thể xuất hiện | Có thể được giới hạn dần bằng các tầng `permits` và `final`. | Không cố định số implementation/hậu duệ. |
| Mở rộng từ bên ngoài | Chỉ trong phạm vi các kiểu trực tiếp được phép và các nhánh còn mở. | Cho phép thêm kiểu con mà không chỉnh danh sách `permits` của tổ tiên. |
| Logic xử lý | Có thể thiết kế theo các biến thể đã biết. | Nên xử lý theo giao diện/hợp đồng và có hành vi dự phòng khi gặp kiểu mới. |
| Quản lý thư viện | Người duy trì kiểm soát danh sách kiểu con trực tiếp. | Cần coi khả năng mở rộng nhánh là một phần của API công khai. |
| Rủi ro khi phát triển | Thay đổi danh sách hoặc loại nhánh có thể ảnh hưởng code phụ thuộc. | Subclass mới có thể xuất hiện mà mã lõi không lường trước nếu chỉ xử lý các class quen thuộc. |

Về kiến trúc, `non-sealed` tạo ra một **đường mở rộng có tên và có hợp đồng**: nhóm phát triển định nghĩa chỗ nào được bổ sung kiểu mới, thay vì buộc phải mở toàn bộ interface gốc.

## 8. Ảnh hưởng tới xử lý phân nhánh và kiểm tra kiểu trong Java 17

Khi một nhánh là `non-sealed`, mã nguồn không thể mặc định “đã thấy hết mọi class triển khai”. Chẳng hạn:

```java
static String describe(DeliveryMethod method) {
    if (method instanceof CounterDelivery) {
        return "Nhận tại quầy";
    }
    if (method instanceof ExtensionDelivery extension) {
        return "Từ nhà cung cấp " + extension.providerName();
    }
    throw new IllegalStateException("Loại giao hàng không hỗ trợ");
}
```

Ở đây, nhánh `ExtensionDelivery` xử lý chung **mọi kiểu triển khai nhánh mở**, kể cả kiểu được thêm sau khi hàm `describe` ra đời. Đường xử lý cuối vẫn được giữ như một phòng vệ rõ ràng cho trường hợp không mong đợi.

Nếu viết như sau thì mã không thể bảo đảm hỗ trợ toàn bộ nhánh mở:

```java
// Thiết kế dễ bỏ sót implementation mới:
if (method instanceof PartnerDelivery) {
    // Chỉ xử lý đúng một class đối tác
}
```

Đối với đối tượng trong nhánh mở, nên ưu tiên **gọi hành vi do interface/abstract class công bố** thay vì phụ thuộc vào danh sách các class cụ thể.

> **Lưu ý phiên bản:** Pattern matching cho `instanceof` là cú pháp chuẩn dùng được trong Java 17. Pattern matching cho `switch` mới ở trạng thái **preview trong Java 17**; không sử dụng nó làm nền tảng bắt buộc cho các ví dụ Java 17 chuẩn. Ngoài ra, đừng nhầm tính “biết được con trực tiếp” của `sealed` với việc tự động có danh sách hữu hạn mọi implementation dưới một nhánh `non-sealed`.

## 9. Tác động đến thiết kế thư viện, plugin và phiên bản API

### 9.1. Khi thư viện công bố một nhánh `non-sealed`

Giả sử library khai báo:

```java
public sealed interface Formatter
        permits StandardFormatter, PluginFormatter {
}

public non-sealed interface PluginFormatter extends Formatter {
    String format(String input);
}
```

Trong dự án thực tế, mỗi kiểu `public` top-level nên đặt trong tệp Java riêng có tên tương ứng; ví dụ rút gọn trên chỉ minh họa quan hệ kiểu. Các lớp triển khai `StandardFormatter` và các cấu hình `permits` còn lại phải được hoàn thiện trong library.

Người dùng có thể bổ sung `class CustomFormatter implements PluginFormatter` ở nơi được phép truy cập interface. Đổi lại, library phải duy trì hợp đồng `format`: đầu vào, đầu ra, lỗi, các bất biến và kỳ vọng liên quan tới dữ liệu phải được mô tả đủ rõ để implementation mới không phá vỡ hành vi.

Những lưu ý khi thiết kế điểm mở rộng:

- **Xác định hợp đồng tối thiểu**: các phương thức nào bắt buộc và hành vi nào phải được bảo đảm?
- **Hạn chế phụ thuộc implementation**: ưu tiên kiểu interface thay vì kiểm tra tên class cụ thể.
- **Chú ý tương thích**: đổi một nhánh đang `non-sealed` thành `sealed` hoặc `final` có thể làm code bên ngoài đang kế thừa bị lỗi khi biên dịch lại hoặc tải class.
- **Duy trì lớp bảo vệ nghiệp vụ**: kiểm tra quyền, dữ liệu và các bất biến tại nơi xử lý phù hợp; `non-sealed` chỉ quản lý cấu trúc kiểu, không tự xác thực code mở rộng.
- **Thiết kế điểm mở có chủ đích**: chỉ mở nhánh cần thiết để phát triển tính năng, không nhất thiết mở toàn bộ mô hình miền.

### 9.2. `non-sealed` không phải cơ chế nạp plugin

`non-sealed` chỉ quy định **quyền kế thừa/triển khai kiểu trong hệ thống type**. Nó không tự:

- tìm các lớp implementation trên classpath/module path;
- khởi tạo đối tượng của các lớp đó;
- đăng ký chúng vào hệ thống;
- bảo đảm mọi implementation tuân thủ ý nghĩa nghiệp vụ của interface.

Để phát hiện và nạp plugin, ứng dụng vẫn cần cơ chế riêng như cấu hình, dependency injection hoặc Java `ServiceLoader` khi thích hợp. Từ khóa `non-sealed` quyết định **có được tạo kiểu con hay không**, còn hệ thống plugin quyết định **làm thế nào tìm và dùng kiểu con đó**.

### 9.3. Không thể dựa vào `non-sealed` để cô lập code không tin cậy

Một đối tác có thể triển khai nhánh mở nhưng tạo ra hành vi ngoài mong đợi. `non-sealed` không đặt giới hạn bảo mật, không kiểm tra dữ liệu hay đảm bảo tính an toàn của code thực thi. Nếu điểm mở rộng nhận dữ liệu nhạy cảm hoặc thực hiện thao tác đặc quyền, hệ thống vẫn cần các cơ chế xác thực, phân quyền, kiểm tra input và kiểm soát thực thi tương ứng.

## 10. Nên chọn `final`, `sealed` hay `non-sealed`?

Khi xây dựng cây kiểu từ một root `sealed`, có thể chọn chính sách cho từng nhánh:

| Nhu cầu thực tế | Lựa chọn phù hợp | Ví dụ |
| --- | --- | --- |
| Không cho phép subclassing của một implementation | `final class` | `CounterDelivery` chỉ mang nghĩa cố định. |
| Chỉ cho phép một số loại con đã định nghĩa | `sealed class` hoặc `sealed interface` | Nhánh nội bộ có `permits` cụ thể. |
| Công bố điểm mở rộng để ứng dụng/đối tác bổ sung kiểu | `non-sealed interface` | `ExtensionDelivery` cho nhiều nhà cung cấp. |
| Cho phép code người dùng kế thừa và tái sử dụng trạng thái/hành vi nền | `non-sealed class` | `UserAuditEvent` làm base class mở. |
| Không cần quản lý tập kiểu con từ root | Class/interface thông thường | Mô hình mở hoàn toàn theo quy tắc Java. |

Một số câu hỏi nên tự đặt ra trước khi chọn `non-sealed`:

1. **Ai sẽ tạo subclass/implementation mới?** Nếu chỉ mã nội bộ sử dụng và tập loại đã biết, nhánh `final` hoặc `sealed` có thể dễ kiểm soát hơn.
2. **Mã xử lý có phụ thuộc mọi kiểu cụ thể đều đã được biết không?** Nếu có, mở nhánh sẽ làm giả định đó không còn an toàn.
3. **Hợp đồng cho implementation mới đã đủ rõ chưa?** Khi giao điểm mở rộng cho bên ngoài, hành vi và bất biến quan trọng hơn danh sách tên class.
4. **API có đảm bảo truy cập từ nơi cần mở rộng không?** Một `non-sealed` nhưng không nhìn thấy được từ module tiêu thụ sẽ không tạo ra khả năng mở rộng hữu ích.
5. **Có chấp nhận duy trì điểm mở đó lâu dài không?** Thu hẹp một nhánh từng công bố là mở có thể ảnh hưởng đến người dùng thư viện.

## 11. Những hiểu nhầm thường gặp

| Nhận định | Điều đúng trong Java 17 |
| --- | --- |
| “Cha `sealed` thì không thể có hậu duệ mới.” | Cha chỉ giới hạn **con trực tiếp**; nhánh `non-sealed` có thể nhận thêm hậu duệ. |
| “Đặt `non-sealed` cho một con thì mọi nhánh của cha đều mở.” | Chỉ nhánh đi qua con đó được mở; `permits` của cha vẫn có hiệu lực. |
| “Muốn thêm đối tác phải sửa `permits` của root.” | Không cần nếu đối tác triển khai một nhánh `non-sealed` được phép. |
| “Có thể thêm `non-sealed` trước bất kỳ class nào.” | Không; nó yêu cầu quan hệ **con trực tiếp** với ít nhất một kiểu `sealed`. |
| “`non-sealed` tự động làm class thành `public`.” | Không; visibility và quy tắc module vẫn áp dụng. |
| “`sealed` bảo đảm xử lý hết mọi implementation trong `if`.” | Không; nhánh `non-sealed` có thể chứa implementation mới chưa được code xử lý lường trước. |
| “`non-sealed` tự đăng ký plugin vào ứng dụng.” | Không; phát hiện và khởi tạo plugin là trách nhiệm riêng của kiến trúc ứng dụng. |

## 12. Bài tập tự luyện

**Bài 1 – Dự đoán khả năng kế thừa**

```java
sealed interface Media permits Photo, Video {
}

final class Photo implements Media {
}

non-sealed interface Video extends Media {
}

class OnlineVideo implements Video {
}
```

Hãy xem xét:

- Có thể thêm `class NewPhoto extends Photo` không? **Không**, vì `Photo` là `final`.
- Có thể thêm `class OfflineVideo implements Video` không? **Có**, nếu thỏa quy tắc truy cập.
- Có thể thêm `class Audio implements Media` trực tiếp không? **Không**, vì `Audio` không nằm trong `Media.permits`.

**Bài 2 – Thiết kế điểm mở rộng**

Một ứng dụng cần mô hình `ReportSource` gồm hai nhánh: `DatabaseSource` là nguồn nội bộ cố định và `ExternalSource` cho phép nhiều dịch vụ bên thứ ba. Hãy:

1. Khai báo `sealed interface ReportSource` với hai nhánh con trực tiếp.
2. Chọn `final` cho nguồn cố định và `non-sealed interface` cho nguồn mở.
3. Định nghĩa một phương thức chung trong `ExternalSource` để mọi đối tác triển khai.
4. Tạo hai class triển khai `ExternalSource` và một phương thức xử lý theo hợp đồng nhánh mở, không kiểm tra từng class đối tác.

**Bài 3 – Phân tích thay đổi API**

Một thư viện đã phát hành `public non-sealed interface ExtensionPoint`, và người dùng có các class `implements ExtensionPoint`. Nếu phiên bản mới đổi `ExtensionPoint` thành `sealed`, những class bên ngoài có thể gặp vấn đề gì? Hãy giải thích vì sao đây không chỉ là thay đổi về cách viết mà còn có thể là **thay đổi phá vỡ khả năng mở rộng của API**.

## Kết luận

`sealed` đặt ranh giới tại các **kiểu con trực tiếp**, còn `non-sealed` là quyết định **mở lại quyền mở rộng tại một nhánh cụ thể**. Tổ hợp `sealed` + `final` + `non-sealed` giúp xây dựng mô hình Java 17 có phần lõi được kiểm soát và những điểm tích hợp vẫn cho phép phát triển độc lập. Khi chọn `non-sealed`, hãy thiết kế hợp đồng hành vi rõ ràng, xử lý theo abstraction và tính đến khả năng xuất hiện implementation mới trong tương lai.

### Tài liệu tham khảo

- [JEP 409: Sealed Classes](https://openjdk.org/jeps/409) — tính năng chính thức của Java 17, gồm `sealed`, `permits` và `non-sealed`.
- [Java Language Specification, Java SE 17 — Chapter 8: Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html) — quy tắc modifier và kế thừa class.
- [Java Language Specification, Java SE 17 — Chapter 9: Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html) — interface và quy tắc sealed interface.
- [JEP 394: Pattern Matching for instanceof](https://openjdk.org/jeps/394) — cú pháp `instanceof` dùng trong ví dụ.
