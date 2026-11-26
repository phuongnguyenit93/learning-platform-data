# Mã thông báo, tham số và nội dung dự phòng

Trong một ứng dụng **Spring Web Flow (SWF)**, người dùng có thể nhập form, gặp lỗi chuyển kiểu, quay lại một `view-state`, nhận cảnh báo hết chỗ rồi xác nhận đặt lịch. Các màn hình phải hiển thị thông báo có ý nghĩa bằng **ngôn ngữ của người dùng**, kể cả khi thiếu bản dịch của một mã. Viết thẳng một chuỗi tiếng Việt trong service khiến việc mở rộng sang tiếng Anh, chỉnh nội dung hay kiểm thử trở nên khó khăn. Giải pháp là tạo **mã thông báo** (message code), **tham số** (arguments) và **nội dung dự phòng** (fallback/default text).

Bài thuộc chương **Thông báo và ngôn ngữ** của module `SPRING_WEB_FLOW`. Trọng tâm là API `MessageContext` và `MessageBuilder` của Web Flow, tích hợp `MessageSource` của Spring, cách tổ chức `messages.properties` cho một flow và cách kiểm chứng thông báo sau validation, redirect, đổi locale hay thiếu key. Ví dụ giả định **Java 17 + Spring Framework 6.x + Spring Web Flow 3.x + Spring MVC**; với SWF 2.5 hoặc 4.x, đối chiếu Javadoc của đúng phiên bản khi áp dụng.

> Trong bài, “mã thông báo” có nghĩa là **key tra cứu bản dịch**, chẳng hạn `booking.visitDate.required`. Nó không phải token xác thực, CSRF token, session ID hay execution key.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của **message code, message arguments, locale và default text**.
2. Ghi thông báo có severity `info`, `warning`, `error` và gắn với field thông qua `MessageContext`.
3. Sử dụng `MessageBuilder.code`, `codes`, `arg`, `resolvableArg` và `defaultText`.
4. Tổ chức bundle theo `messages.properties`, `messages_vi.properties` và `messages_en.properties` cho từng flow hoặc dùng `MessageSource` chung của ứng dụng.
5. Hiểu thứ tự fallback của mã cụ thể, mã tổng quát, bản dịch theo locale và nội dung dự phòng, đồng thời nhận diện các điểm phụ thuộc cấu hình.
6. Cấu hình và kiểm thử lỗi `typeMismatch` sinh tự động khi bind form.
7. Đảm bảo thông báo đúng ngôn ngữ sau redirect, khi người dùng đổi locale, mở nhiều tab hoặc gặp lỗi nghiệp vụ.

## 2. Bốn thành phần của một thông báo được bản địa hóa

Xét thông báo khi người dùng chọn ngày `2026-02-28` đã qua:

| Thành phần | Giá trị ví dụ | Nhiệm vụ |
| --- | --- | --- |
| **Code** | `booking.visitDate.notFuture` | Khóa ổn định để tra bản dịch |
| **Arguments** | `"2026-02-28"` | Dữ liệu thay đổi theo request, gán vào `{0}` |
| **Locale** | `vi-VN` hoặc `en-US` | Xác định ngôn ngữ/cách định dạng |
| **Default text** | `Ngày đã chọn không hợp lệ.` | Nội dung dùng khi không tìm thấy code trong nguồn thông báo |

Một mã có thể cho ra các câu khác nhau:

~~~properties
# messages_vi.properties
booking.visitDate.notFuture=Ngày {0} phải sau hôm nay.
~~~

~~~properties
# messages_en.properties
booking.visitDate.notFuture=The date {0} must be after today.
~~~

Tham số `{0}` được chèn vào bản dịch theo chỉ số, không cần nối chuỗi cứng trong Java. Với cùng mã và giá trị, đầu ra phụ thuộc locale:

| Locale | Kết quả minh họa |
| --- | --- |
| `vi-VN` | Ngày 2026-02-28 phải sau hôm nay. |
| `en-US` | The date 2026-02-28 must be after today. |

Ví dụ chỉ minh họa kỹ thuật thay tham số; ngày cụ thể có hợp lệ hay không do **validator tại thời điểm request** quyết định. Thông báo không thực hiện validation.

## 3. Đường đi của một thông báo trong Web Flow

~~~mermaid
flowchart LR
    A["HTTP request / event next"] --> B["View-state binding"]
    B --> C["Validator / Action"]
    C --> D["MessageBuilder: code + args + defaultText"]
    D --> E["MessageContext của flow"]
    E --> F["MessageSource / bundle theo Locale"]
    F --> G["Message đã resolve"]
    G --> H["Render lỗi field, cảnh báo hoặc thông tin"]
~~~

**`MessageContext`** là vùng ghi nhận các thông báo phát sinh trong quá trình flow execution. Nó có thể chứa thông báo từ validator, action và lỗi binding do framework tạo. Theo tài liệu Web Flow, thông báo trong context **được giữ qua redirect của flow** để view đích render; tuy vậy đây không phải kho lưu thông báo vĩnh viễn. Khi execution kết thúc, hết hạn hoặc view không còn phù hợp, ứng dụng cần thiết kế đường hiển thị kết quả khác.

**`MessageBuilder`** chỉ mô tả cách tạo thông báo; khi thêm vào `MessageContext`, thông báo được resolve bằng `MessageSource` được cấu hình. Điều này tách **logic nghiệp vụ quyết định lỗi** khỏi **nội dung ngôn ngữ**.

### 3.1. Phân biệt các cơ chế dễ nhầm

| Cơ chế | Mục đích | Ví dụ |
| --- | --- | --- |
| `MessageContext` (Web Flow) | Tập thông báo trong quá trình xử lý flow | “Ngày nhận phòng không hợp lệ” gắn với field |
| `MessageSource` (Spring) | Tra nội dung theo code/arguments/locale | `booking.visitDate.required` → câu tiếng Việt |
| `resourceBundle` (EL của Web Flow) | Truy cập bundle từ flow/view | Tra tiêu đề, nhãn hoặc thông báo tĩnh |
| `flashScope` (Web Flow) | Scope ngắn hạn cho dữ liệu qua lần render | Một chuỗi trạng thái được lưu cho view kế tiếp |
| Flash attributes (Spring MVC) | Chuyển model attributes qua redirect MVC | Thông báo sau POST controller |
| `BindingResult` (Spring MVC) | Kết quả binding/validation model | `typeMismatch` hoặc `NotBlank` |

Không coi chúng là một object. `MessageContext` có hành vi sống qua redirect riêng của Web Flow; không cần phải sao chép mọi message sang `HttpSession` hay MVC flash attributes.

## 4. Severity và vị trí hiển thị

Web Flow chủ yếu dùng ba nhóm mức độ cho thông báo giao diện:

| Severity | Builder API | Khi nào dùng | Trình bày gợi ý |
| --- | --- | --- | --- |
| Thông tin | `info()` | Đã tiếp nhận yêu cầu, lưu nháp thành công | Thông báo trạng thái thông thường |
| Cảnh báo | `warning()` | Dịch vụ sắp hết chỗ, giá có thể thay đổi | Nêu rủi ro và bước tiếp theo |
| Lỗi | `error()` | Ngày sai định dạng, trường bắt buộc trống | Đặt cạnh field và tóm tắt lỗi |

Javadoc `MessageBuilder` cũng có `fatal()`; hãy kiểm tra API và chiến lược hiển thị của phiên bản SWF đang dùng trước khi triển khai mức severity đặc biệt này. Trong những flow form thông thường, ba mức trên là đủ.

**Gắn nguồn (source)** để lỗi xuất hiện đúng vị trí. Ví dụ `source("visitDate")` cho phép view tìm các lỗi của trường `visitDate`, còn thông báo không có source thường phù hợp làm banner tổng quát. Source là **định danh field hoặc object**, không phải mã i18n; `source("visitDate")` và `code("booking.visitDate.required")` có vai trò khác nhau.

## 5. Các phương thức trọng tâm của MessageBuilder

| API | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `code("booking.required")` | Thêm một mã để tra cứu | Thông báo thiếu dữ liệu |
| `codes("booking.date.required", "booking.required")` | Thêm nhiều mã theo thứ tự ưu tiên | Cụ thể trước, tổng quát sau |
| `arg(value)` / `args(values...)` | Truyền dữ liệu thường vào `{0}`, `{1}` | Ngày, số suất, mã booking |
| `resolvableArg("booking.field.visitDate")` | Tham số cũng được tra như mã bản dịch | Tên trường “ngày tham gia” |
| `defaultText("...")` | Văn bản dự phòng nếu không resolve được mã | Câu có ý nghĩa khi thiếu bản dịch |
| `source("visitDate")` | Gắn message với field | Lỗi hiển thị bên cạnh input |
| `info()` / `warning()` / `error()` | Chọn mức độ | Banner/lỗi field |
| `build()` | Tạo `MessageResolver` để thêm vào context | `messageContext.addMessage(...)` |

Một đoạn Java hợp lệ về API, giả định nằm trong method có đối tượng `MessageContext messages`:

~~~java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;

messages.addMessage(new MessageBuilder()
    .error()
    .source("visitDate")
    .codes("booking.visitDate.required", "booking.form.required")
    .resolvableArg("booking.field.visitDate")
    .defaultText("Vui lòng nhập ngày tham gia.")
    .build());
~~~

Trong ví dụ này, resolver thử mã `booking.visitDate.required` trước; nếu không tìm thấy, thử `booking.form.required`. Tham số đầu tiên được resolve từ `booking.field.visitDate` khi cần, để bản dịch tổng quát có thể nói “Trường ngày tham gia là bắt buộc”. Nếu không giải quyết được các mã, `defaultText` là phương án cuối cùng.

### 5.1. `arg` khác `resolvableArg` thế nào?

Khi truyền:

~~~java
.arg("booking.field.visitDate")
~~~

thì `{0}` thường là **chuỗi literal** `booking.field.visitDate`. Nhưng với:

~~~java
.resolvableArg("booking.field.visitDate")
~~~

Spring có thể tra chính mã này qua `MessageSource` để lấy “ngày tham gia” hoặc “visit date”. Kỹ thuật này hữu ích khi muốn viết **một thông báo chung cho nhiều field**.

Nếu đối số là số lượng `2` hoặc mã đơn hàng đã tạo, hãy dùng `arg(2)` hay `arg(bookingCode)`. Không dùng `resolvableArg` cho mọi chuỗi đầu vào người dùng: các giá trị tùy ý không phải message code và có thể tạo kết quả khó đoán.

### 5.2. Nhiều tham số có thứ tự

~~~properties
booking.capacity.limit=Tối đa {0,number,integer} khách cho dịch vụ {1}.
~~~

~~~java
messages.addMessage(new MessageBuilder()
    .warning()
    .code("booking.capacity.limit")
    .arg(4)
    .arg("Workshop A")
    .defaultText("Số lượng khách vượt giới hạn.")
    .build());
~~~

`{0}` là số `4`, `{1}` là tên dịch vụ. Việc đổi thứ tự trong bản dịch phải giữ đúng ý nghĩa tham số; nên ghi rõ “argument contract” trong tài liệu của mỗi code có tham số.

## 6. Quy ước đặt mã thông báo

Nên dùng các key có **ngữ nghĩa ổn định**, chẳng hạn:

| Nhóm | Ví dụ | Ngữ cảnh |
| --- | --- | --- |
| Nhãn và tiêu đề | `booking.review.title` | Tiêu đề màn hình review |
| Field label | `booking.field.visitDate` | Tên trường ngày tham gia |
| Validation cụ thể | `booking.visitDate.required` | Bắt buộc nhập ngày |
| Validation chung | `booking.form.required` | Một field bất kỳ bị thiếu |
| Lỗi binding | `booking.visitDate.typeMismatch` | Không parse được ngày |
| Nghiệp vụ | `booking.slot.unavailable` | Dịch vụ hết chỗ |
| Thành công | `booking.confirmed` | Đặt chỗ được xác nhận |
| Hệ thống | `common.error.unexpected` | Lỗi chung có thể thử lại |

Đặt code theo **module/feature + ngữ nghĩa + loại**, không đặt theo câu đang dịch. Ví dụ `booking.confirmed` vẫn đúng nếu biên tập nội dung tiếng Việt từ “Đã xác nhận” sang “Đặt chỗ thành công”.

Những mã gắn với field cần khớp naming của binder hoặc được adapter chuyển đổi có chủ đích. Mã tổng quát nên được tái sử dụng có kiểm soát, tránh một code `error` cho mọi sự cố khiến nội dung không rõ ràng.

Không dùng dữ liệu tùy ý từ request làm message code: một key phải đến từ **mã được xác định trong source code hoặc policy đã kiểm soát**, còn dữ liệu động đi qua arguments.

## 7. Tổ chức message bundles theo flow và ứng dụng

Spring Web Flow hỗ trợ **bundle riêng cho một flow**: đặt các file `messages.properties` cạnh file định nghĩa flow, ví dụ:

~~~text
src/main/resources/
  flows/
    booking/
      booking-flow.xml
      messages.properties
      messages_vi.properties
      messages_en.properties
  messages.properties
  messages_vi.properties
  messages_en.properties
~~~

Nhóm ở `flows/booking/` là **bundle của flow**, được Web Flow tìm theo convention nêu trong reference. Nhóm ở root classpath thường là **bundle chung của ứng dụng** do Spring Boot/Spring MVC cấu hình. Khi cần tra key từ nhiều nguồn, thứ tự tìm và cơ chế fallback cụ thể phụ thuộc việc registry, `MessageSource` và các parent sources được cấu hình thế nào; nên viết test cho từng key đang dùng thay vì phỏng đoán precedence.

### 7.1. Bundle gốc — `flows/booking/messages.properties`

Bundle gốc có thể chứa nội dung dự phòng theo ngôn ngữ mặc định của sản phẩm. Trong ví dụ chọn **tiếng Anh** để thể hiện rõ khi thiếu một key tiếng Việt:

~~~properties
booking.review.title=Review reservation
booking.field.visitDate=visit date
booking.field.email=email address
booking.visitDate.required=Please enter a visit date.
booking.form.required=The {0} field is required.
booking.visitDate.notFuture=The date {0} must be in the future.
booking.slot.unavailable=No places are available for {0}.
booking.capacity.limit=At most {0,number,integer} guests can join {1}.
booking.confirmed=Reservation {0} was confirmed.
booking.remaining=Only {0,number,integer} places remain.
booking.visitDate.typeMismatch=Enter the date using yyyy-MM-dd.
typeMismatch=The {0} field has an invalid value.
common.error.unexpected=We could not finish the request. Please try again.
~~~

### 7.2. Tiếng Việt — `flows/booking/messages_vi.properties`

~~~properties
booking.review.title=Xem lại đặt chỗ
booking.field.visitDate=ngày tham gia
booking.field.email=địa chỉ email
booking.visitDate.required=Vui lòng nhập ngày tham gia.
booking.form.required=Trường {0} là bắt buộc.
booking.visitDate.notFuture=Ngày {0} phải sau hôm nay.
booking.slot.unavailable=Dịch vụ {0} hiện không còn chỗ.
booking.capacity.limit=Tối đa {0,number,integer} khách được tham gia {1}.
booking.confirmed=Đã xác nhận đặt chỗ {0}.
booking.remaining=Chỉ còn {0,number,integer} chỗ.
booking.visitDate.typeMismatch=Ngày phải theo dạng yyyy-MM-dd.
typeMismatch=Giá trị của trường {0} không đúng định dạng.
common.error.unexpected=Không thể hoàn tất yêu cầu. Hãy thử lại.
~~~

### 7.3. Tiếng Anh — `flows/booking/messages_en.properties`

Nếu sản phẩm có phương ngữ tiếng Anh cần tùy biến, thêm file `messages_en.properties` (ví dụ thay “reservation” bằng “booking”). Nếu không cần biến thể, **bundle gốc bằng tiếng Anh đã đủ cho fallback cơ bản**. Có thể thêm `messages_en_US.properties` hoặc `messages_vi_VN.properties` cho cách diễn đạt riêng theo vùng, nhưng chỉ khi có nhu cầu.

**Luôn có `messages.properties`**, kể cả khi phần lớn nội dung nằm trong file ngôn ngữ. Spring Boot chỉ tự cấu hình global message source khi tìm thấy default bundle theo các basename đã chỉ định; Web Flow cũng khuyến nghị bundle mặc định cho flow.

### 7.4. Bundle chung với Spring Boot

Ví dụ `application.properties`:

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

`spring.messages.basename` áp dụng cho message source do **Spring Boot** tự cấu hình, không phải đường dẫn bắt buộc để Web Flow tìm bundle đặt cạnh flow XML. Nếu ứng dụng sử dụng đồng thời hai loại, kiểm tra nơi key được tìm khi có trùng tên và nơi defaultText được áp dụng.

Tắt `fallback-to-system-locale` giúp tránh máy chủ production tình cờ dùng ngôn ngữ hệ điều hành khác với chính sách ứng dụng. Cấu hình này tác động tới message source do Boot quản lý; kiểm tra riêng nếu flow tạo hierarchy message source khác.

## 8. Hiểu chính xác các tầng fallback

“Fallback” có thể xảy ra ở **hai chiều khác nhau**: thử **mã thay thế** và thử **bundle/locale thay thế**. Sau đó mới đến nội dung `defaultText` nếu không resolve được mã.

~~~mermaid
flowchart TD
    A["MessageBuilder.codes(codeCụThể, codeChung)"] --> B{"Code cụ thể có trong nguồn thông báo?"}
    B -->|"Có"| C["Resolve theo Locale rồi thay tham số"]
    B -->|"Không"| D{"Code chung có trong nguồn thông báo?"}
    D -->|"Có"| C
    D -->|"Không"| E{"Có defaultText?"}
    E -->|"Có"| F["Hiển thị defaultText"]
    E -->|"Không"| G["Phụ thuộc MessageSource/config: lỗi thiếu message hoặc lộ key"]
    C --> H["Render thông báo"]
    F --> H
~~~

Sơ đồ chỉ đơn giản hóa mức code. Với **mỗi code**, `MessageSource` có thể tìm bản dịch qua thứ tự locale cụ thể, locale ít cụ thể hơn và bundle mặc định theo implementation/configuration. Do đó thứ tự tìm thực tế là sự kết hợp giữa **danh sách code** và **chuỗi locale fallback**, cùng hierarchy nguồn thông báo nếu có.

### 8.1. Fallback theo mức cụ thể của code

~~~java
new MessageBuilder()
    .error()
    .source("visitDate")
    .codes("booking.visitDate.required", "booking.form.required")
    .resolvableArg("booking.field.visitDate")
    .defaultText("Vui lòng nhập ngày tham gia.")
    .build();
~~~

Nếu `booking.visitDate.required` có mặt, thông báo riêng được chọn. Nếu key riêng bị thiếu nhưng `booking.form.required` có mặt, dùng câu tổng quát với tên field truyền vào. Chỉ khi **cả hai code đều không resolve được** mới dùng `defaultText`.

**Cảnh báo:** nếu code chung đang tồn tại trong bundle gốc bằng tiếng Anh mà code riêng thiếu ở `messages_vi.properties`, việc hiển thị có thể fallback sang tiếng Anh ở code riêng trước khi tới mã chung tiếng Việt tùy cách nguồn hợp nhất bundle và resolve locale. Vì vậy cần **kiểm thử thứ tự precedence cụ thể**, nhất là khi có nhiều basename/parent message source.

### 8.2. Fallback theo locale

Với locale `vi-VN`, nguồn bundle theo convention có thể tìm:

~~~text
messages_vi_VN.properties   (nếu có)
messages_vi.properties      (nếu có)
messages.properties         (bundle gốc)
~~~

Các biến thể ngôn ngữ khác như `en-GB` hoặc `en-US` có chuỗi fallback tương ứng. Việc rơi về locale mặc định của JVM, parent message source hoặc một basename khác còn phụ thuộc cấu hình; không nên mô tả một thứ tự duy nhất như thể áp dụng cho mọi ứng dụng.

Ví dụ `booking.confirmed` có trong bundle tiếng Việt thì người dùng `vi-VN` thấy câu tiếng Việt. Nếu chưa dịch một key, hệ thống có thể dùng câu tiếng Anh từ bundle gốc. Đây là **dự phòng để không mất thông tin**; mục tiêu sản phẩm vẫn là dịch đủ các key xuất hiện trong hành trình quan trọng.

### 8.3. `defaultText` và `MessageSource.getMessage`

Trong Spring `MessageSource` có hai dạng quan trọng:

~~~java
import java.util.Locale;
import org.springframework.context.MessageSource;

// Trả fallback đã cung cấp nếu key không tìm được.
String label = messageSource.getMessage(
    "booking.field.unknown", null, "Trường dữ liệu", Locale.forLanguageTag("vi-VN"));

// Dạng không có fallback: có thể ném NoSuchMessageException.
String title = messageSource.getMessage(
    "booking.review.title", null, Locale.forLanguageTag("vi-VN"));
~~~

Trong Web Flow, `MessageBuilder.defaultText` làm vai trò fallback cho một message resolver. Nếu không có `defaultText` và key không thể resolve, hành vi có thể dẫn đến lỗi không tìm thấy message hoặc lộ raw code, phụ thuộc cấu hình `MessageSource`. Không để thông báo quan trọng dựa vào may rủi.

### 8.4. Không xem raw code là thông báo người dùng

Cấu hình `useCodeAsDefaultMessage` của Spring message source có thể dùng code làm văn bản thay thế. Chế độ đó tiện lúc phát triển để nhìn thấy key thiếu, nhưng production nên có bản dịch hoặc fallback rõ ràng. Một thông báo như `booking.slot.unavailable` không giúp người dùng hiểu phải làm gì.

## 9. Tham số, MessageFormat và lỗi dấu nháy

Spring thường sử dụng cú pháp `java.text.MessageFormat` khi format message có arguments:

| Cú pháp | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `{0}` | Tham số thứ nhất | `bookingCode` |
| `{1}` | Tham số thứ hai | `serviceName` |
| `{0,number,integer}` | Số nguyên theo locale | `2` |
| `{0,number,#,##0.00}` | Số có pattern | `1250.5` |
| `{0,date,short}` | Ngày theo locale (với kiểu ngày phù hợp) | `java.util.Date` |

### 9.1. Ví dụ parameter contract ổn định

~~~properties
booking.confirmed=Đã xác nhận đặt chỗ {0}.
booking.capacity.limit=Tối đa {0,number,integer} khách được tham gia {1}.
~~~

~~~java
messages.addMessage(new MessageBuilder()
    .info()
    .code("booking.confirmed")
    .arg("BK-2027-001")
    .defaultText("Đặt chỗ đã được xác nhận.")
    .build());
~~~

Nếu thay mã `BK-2027-001` bằng ID khác, chỉ cần thay argument; các bản dịch không phải sửa. Khi có nhiều tham số, tài liệu API phải ghi rõ thứ tự và kiểu. Ví dụ:

~~~text
booking.capacity.limit:
  {0} = maximumGuests (Integer)
  {1} = serviceTitle  (String)
~~~

Không truyền `LocalDate` trực tiếp cho pattern `{0,date}` rồi mặc định rằng `MessageFormat` biết xử lý: một số cách format yêu cầu kiểu ngày tương thích với `java.util.Date`. Với `java.time`, có thể format bằng `DateTimeFormatter`/Spring Formatter trước khi truyền, hoặc dùng cơ chế format thích hợp cho loại đối tượng trong cấu hình đang dùng. Nhớ dùng cùng locale dự kiến khi format.

### 9.2. Dấu nháy đơn, ngoặc nhọn và nội dung không cố định

`MessageFormat` xem dấu nháy đơn `'` là ký hiệu escape ở nhiều vị trí. Nếu câu có dấu nháy đơn, đôi khi phải viết **hai dấu nháy đơn liên tiếp** trong pattern:

~~~properties
# Khi MessageFormat xử lý pattern với tham số:
booking.example=It''s time to confirm {0}.
~~~

Thông điệp ở mã trên sẽ hiển thị theo ý “It's time to confirm ...” khi được format. Với một message không có arguments, tùy thiết lập `alwaysUseMessageFormat` mà quá trình parse pattern có thể khác; hãy kiểm thử đúng cách `MessageSource` được cấu hình. Khi cần in dấu ngoặc nhọn literal, dùng quy tắc escape của `MessageFormat`, không giả định `{` và `}` luôn được giữ nguyên.

Nếu bản dịch dùng chuỗi có dấu nháy, số, phần trăm hoặc đơn vị tiền tệ, test **sau khi được resolve** để không chỉ so sánh chuỗi trong file properties.

### 9.3. Phân biệt dữ liệu để format và nội dung cần bảo vệ

Các arguments có thể đến từ người dùng, ví dụ tên dịch vụ do họ tạo. Bản dịch là **template đáng tin cậy** trong source code; arguments là **dữ liệu không tin cậy** và phải được escape khi chèn vào HTML, attribute, JavaScript hoặc URL. Không tự nối HTML từ `message.text` và các input rồi render bằng cơ chế không escape.

Không đưa mật khẩu, session ID, access token, địa chỉ hoặc thông tin nhạy cảm không cần thiết làm argument. Với thông báo về quyền truy cập, tránh hiển thị chi tiết bản ghi của người khác.

## 10. Mã thông báo cho lỗi binding được Web Flow sinh tự động

Web Flow có thể tự tạo lỗi khi dữ liệu từ form không thể bind vào property Java, ví dụ người dùng nhập `"abc"` cho số khách hoặc `"ngay-mai"` cho `LocalDate`. Với lỗi chuyển kiểu `typeMismatch`, reference mô tả cơ chế ưu tiên key gắn với **tên model và property**, sau đó có thể thử key tổng quát.

Ví dụ với class `Booking` có property `visitDate`:

~~~properties
# Lỗi cụ thể của một field/model:
booking.visitDate.typeMismatch=Ngày phải theo dạng yyyy-MM-dd.

# Lỗi chung; tên field được truyền vào như argument {0}:
typeMismatch=Giá trị của trường {0} không đúng định dạng.
~~~

| Khi nào | Key thường được thử | Nội dung dự kiến |
| --- | --- | --- |
| `Booking.visitDate` nhận chuỗi sai kiểu | `booking.visitDate.typeMismatch` | Ngày phải theo dạng yyyy-MM-dd. |
| Không có key riêng | `typeMismatch` | Giá trị của trường [tên field] không đúng định dạng. |

**Tên key phải khớp cơ chế tạo error codes của phiên bản/mô hình thực tế.** Nếu class là `BookingForm`, tên object/model có thể khác `booking`; khi đó key cụ thể sẽ khác. Ngoài Web Flow error code resolver, Spring MVC Bean Validation có thể sinh các code theo thứ tự từ cụ thể đến tổng quát dựa trên `MessageCodesResolver`. Hãy quan sát code thực tế trong `BindingResult`/`MessageContext` trước khi “sửa” file properties bằng cách đoán tên.

### 10.1. Conversion error khác business validation error

| Lỗi | Nơi phát hiện | Ví dụ message code |
| --- | --- | --- |
| Không parse được ngày | Binder/conversion | `booking.visitDate.typeMismatch` |
| Ngày có kiểu hợp lệ nhưng đã qua | Validator | `booking.visitDate.notFuture` |
| Số khách bằng 0 | Bean/business validation | `booking.guests.minimum` |
| Slot vừa hết chỗ | Service | `booking.slot.unavailable` |
| Không có quyền xem bản nháp | Authorization | `common.error.accessDenied` |

Không cần ép tất cả lỗi thành `typeMismatch`. Mỗi loại cần thông điệp phù hợp để người dùng biết **sửa dữ liệu**, **chọn lại dịch vụ** hay **đăng nhập/làm lại**.

### 10.2. Required binding và Bean Validation

Trong XML:

~~~xml
<view-state id="details" view="booking/details" model="booking">
    <binder>
        <binding property="visitDate" required="true"/>
    </binder>
    <transition on="next" to="review"/>
</view-state>
~~~

`required="true"` là yêu cầu của binder cho field; bên cạnh đó, `@NotNull` hoặc validator riêng có thể có code và thông báo riêng. Không suy rằng lỗi required luôn có key giống `typeMismatch` hoặc luôn là `NotNull`. Kiểm tra thực tế error code được tạo để chọn key đúng và tránh hiển thị **hai lỗi giống nhau** cho cùng một vấn đề.

## 11. Ví dụ hoàn chỉnh về luồng và Action phát thông báo

Giả sử một flow đặt lịch có model `Booking` với `LocalDate visitDate` và `String confirmationCode`. Validator phải kiểm tra ngày và service mới quyết định còn suất hay không.

### 11.1. Java action tạo message code và fallback

~~~java
package com.example.booking.flow;

import java.time.Clock;
import java.time.LocalDate;
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;
import org.springframework.stereotype.Service;

@Service("bookingMessages")
public class BookingMessageActions {
    private final Clock clock;

    public BookingMessageActions(Clock clock) {
        this.clock = clock;
    }

    public boolean validateVisitDate(Booking booking, MessageContext messages) {
        LocalDate date = booking.getVisitDate();
        if (date == null) {
            messages.addMessage(new MessageBuilder()
                .error()
                .source("visitDate")
                .codes("booking.visitDate.required", "booking.form.required")
                .resolvableArg("booking.field.visitDate")
                .defaultText("Vui lòng nhập ngày tham gia.")
                .build());
            return false;
        }

        if (!date.isAfter(LocalDate.now(clock))) {
            messages.addMessage(new MessageBuilder()
                .error()
                .source("visitDate")
                .code("booking.visitDate.notFuture")
                .arg(date.toString())
                .defaultText("Ngày đã chọn không hợp lệ.")
                .build());
            return false;
        }
        return true;
    }

    public void warnUnavailable(String serviceName, MessageContext messages) {
        messages.addMessage(new MessageBuilder()
            .warning()
            .code("booking.slot.unavailable")
            .arg(serviceName)
            .defaultText("Dịch vụ tạm thời không còn chỗ.")
            .build());
    }

    public void confirmMessage(String bookingCode, MessageContext messages) {
        messages.addMessage(new MessageBuilder()
            .info()
            .code("booking.confirmed")
            .arg(bookingCode)
            .defaultText("Đã xác nhận đặt chỗ.")
            .build());
    }
}
~~~

Đây là class minh họa có thể đưa vào một ứng dụng khi đã định nghĩa `Booking` và bean `Clock`. Nó dùng `date.toString()` để đưa giá trị ISO thành argument String, tránh ngộ nhận rằng `MessageFormat` sẽ tự định dạng mọi kiểu `java.time`. Ở production, validator còn phải xem múi giờ của dịch vụ, quy tắc đặt lịch và giới hạn ngày.

Ví dụ bean `Clock`:

~~~java
@Bean
Clock bookingClock() {
    return Clock.systemUTC();
}
~~~

Nếu “hôm nay” được định nghĩa theo múi giờ Việt Nam, thay bằng `Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"))` và test bằng `Clock.fixed(...)`; không để hai tầng validation dùng múi giờ khác nhau.

### 11.2. Flow XML sử dụng biến đặc biệt `messageContext`

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <var name="booking" class="com.example.booking.flow.Booking"/>

    <view-state id="details" view="booking/details" model="booking">
        <binder>
            <binding property="visitDate" required="true"/>
        </binder>
        <transition on="next" to="review">
            <evaluate expression="bookingMessages.validateVisitDate(booking, messageContext)"/>
        </transition>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="review" view="booking/review">
        <transition on="back" to="details" bind="false"/>
        <transition on="confirm" to="finished"/>
    </view-state>

    <end-state id="finished" view="booking/finished"/>
    <end-state id="cancelled" view="booking/cancelled"/>
</flow>
~~~

Đây là một flow minh họa **điều hướng và thông báo**, chưa đủ logic commit thực tế. `Booking`, Spring MVC integration, view templates và validation rules phải được ứng dụng cung cấp. Kết quả đặt chỗ thật cần service kiểm tra quyền, tình trạng slot, transaction và idempotency.

Khi `validateVisitDate` trả `false`, action trên transition không cho flow chuyển thành công sang `review`; thông báo đã ghi ở `messageContext` phục vụ render lại `details`. Lỗi parse `visitDate` có thể phát sinh trước khi action chạy, khi đó framework phát message binding tương ứng.

### 11.3. Đọc thông báo theo source

`MessageContext` hỗ trợ:

~~~java
org.springframework.binding.message.Message[] all =
    messages.getAllMessages();

org.springframework.binding.message.Message[] dateMessages =
    messages.getMessagesBySource("visitDate");

boolean hasErrors = messages.hasErrorMessages();
~~~

`getAllMessages()` dùng cho một danh sách thông báo tổng quan; `getMessagesBySource("visitDate")` dùng để hiển thị lỗi bên cạnh field. Hãy phân biệt **thông báo field** với **thông báo global**, tránh mất lỗi global khi view chỉ render các field error.

### 11.4. Resource bundle trong biểu thức flow

Web Flow cung cấp biến EL `resourceBundle` để đọc message resource, ví dụ:

~~~xml
<on-entry>
    <set name="flashScope.reviewTitle"
         value="resourceBundle['booking.review.title']"/>
</on-entry>
~~~

Đây là **trích đoạn** trong một state có `<on-entry>`; cú pháp và phạm vi biến có thể được kiểm thử theo expression parser/config thực tế. Với nội dung tĩnh cần luôn theo locale hiện tại, ưu tiên tra code khi render view thay vì lưu sẵn chuỗi đã dịch vào `flowScope` trong thời gian dài.

## 12. Hiển thị thông báo bằng Spring MVC/Thymeleaf hoặc JSF

Mã nguồn action đã ghi message, nhưng người dùng chỉ nhìn thấy khi **view render đúng phần chứa thông báo**. Cần kiểm tra cả lỗi field, cảnh báo global và thông tin xác nhận, đặc biệt khi flow render lại cùng state vì validation thất bại.

### 12.1. Thông báo tĩnh trong Thymeleaf

Trong template Thymeleaf tích hợp Spring MVC, message expression tham chiếu code:

~~~html
<h1 th:text="#{booking.review.title}">Xem lại đặt chỗ</h1>
<label for="visitDate" th:text="#{booking.field.visitDate}">
    Ngày tham gia
</label>
~~~

Đây là việc tra **message của view** theo locale và message source mà Thymeleaf dùng. Nó khác với việc thêm message resolver vào `MessageContext` của Web Flow. Hai cơ chế nên sử dụng **cùng mã/bản dịch hoặc bộ tài nguyên đã đồng bộ**, nhưng không tự mặc định chúng chia sẻ cùng một instance `MessageSource` khi ứng dụng cấu hình nhiều source.

### 12.2. Lỗi gắn với field của flow

Một mẫu form dùng Spring binding trong Thymeleaf:

~~~html
<form method="post" th:action="${flowExecutionUrl}"
      th:object="${booking}">
    <label for="visitDate" th:text="#{booking.field.visitDate}">
        Ngày tham gia
    </label>
    <input id="visitDate" type="date" th:field="*{visitDate}">

    <p class="field-error" role="alert"
       th:if="${#fields.hasErrors('visitDate')}"
       th:errors="*{visitDate}">
        Ngày không hợp lệ
    </p>

    <button type="submit" name="_eventId_next">Tiếp tục</button>
</form>
~~~

Đoạn mẫu giả định `MvcViewFactoryCreator` và cơ chế Spring Bean Binding/Thymeleaf được cấu hình để expose các lỗi field qua binding API của Spring. **Cần kiểm tra việc bridge từ Web Flow `MessageContext` tới view thực tế**: không phải mọi cấu hình ViewResolver đều tự đưa mọi loại message vào `#fields`.

Nếu cần render message trực tiếp từ `MessageContext`, có thể dùng API `getAllMessages()` hoặc `getMessagesBySource("visitDate")` tại lớp view/adapter. Thiết kế CSS/HTML cần phân biệt error, warning và info; đảm bảo văn bản hiện được với người dùng bàn phím và công nghệ hỗ trợ, không chỉ đổi màu viền input.

### 12.3. Hiển thị trong JSF

Với Spring Faces/JSF, tài liệu Web Flow mô tả biến EL `resourceBundle`:

~~~xml
<h:outputText value="#{resourceBundle.bookingConfirmed}"/>
~~~

Nếu dùng JSF, xem cấu hình `FacesMessage`, component library, `spring-faces` và JSF version phù hợp với SWF đang chạy. Web Flow 3.x nằm trên Spring 6/Jakarta với JSF 4.0+, còn Web Flow 4.x cần thế hệ JSF mới hơn theo reference của dòng đó. Không lấy nguyên cách render của JSP/JSF gắn vào Thymeleaf mà không kiểm tra tích hợp tương ứng.

### 12.4. Thông báo lỗi ở cấp form

Ngoài lỗi cụ thể `source("visitDate")`, flow có thể phát cảnh báo chung:

~~~java
messages.addMessage(new MessageBuilder()
    .error()
    .code("common.error.unexpected")
    .defaultText("Không thể hoàn tất yêu cầu. Hãy thử lại.")
    .build());
~~~

Thông báo trên không gắn `source`, phù hợp cho banner đầu form hoặc vùng lỗi chung. Trong UI, có thể hiển thị một bản tóm tắt lỗi kèm liên kết đến field bị sai. Không giấu thông báo global chỉ vì view đang tập trung render thông báo theo từng property.

## 13. Locale, thay ngôn ngữ trong khi flow đang chạy và redirect

**Locale** là bối cảnh ngôn ngữ/khu vực được chọn cho request. Spring MVC có `LocaleResolver`/`LocaleContextResolver`, có thể dựa trên `Accept-Language`, cookie, session hoặc chính sách do ứng dụng cấu hình. Spring Web Flow dựa trên MVC/Servlet ở lớp web, nên cần kiểm tra locale được đưa vào message resolution trong từng request của execution.

### 13.1. Ba cách xác định locale thường gặp

| Cách | Nguồn | Cần lưu ý |
| --- | --- | --- |
| `AcceptHeaderLocaleResolver` | Header `Accept-Language` của trình duyệt | Không phải nơi lưu lựa chọn ngôn ngữ tùy ý của người dùng |
| `CookieLocaleResolver` | Cookie có locale do ứng dụng thiết lập | Cần chính sách cookie và HTTPS phù hợp |
| `SessionLocaleResolver` | Thuộc tính trong HTTP session | Mất khi session kết thúc; cần xử lý khi người dùng logout |

Nếu sử dụng `LocaleChangeInterceptor` với tham số như `lang=vi`, phải chọn resolver **có thể thay locale** và đảm bảo interceptor áp dụng cho các URL được Web Flow xử lý; resolver chỉ đọc header có thể không hỗ trợ `setLocale` theo cách mong đợi.

Ngôn ngữ giao diện không phải một kiểm tra phân quyền. Người dùng có thể thay query parameter `lang`, nhưng điều đó không được làm thay đổi danh tính, quyền sở hữu bản nháp hay kết quả giao dịch.

### 13.2. Điều gì xảy ra khi người dùng đổi từ tiếng Việt sang tiếng Anh?

Giả sử:

1. Người dùng mở `details` với locale `vi-VN`.
2. Validation ghi code `booking.visitDate.required`, view hiển thị tiếng Việt.
3. Người dùng đổi ngôn ngữ sang `en-US` rồi gửi lại form.
4. Request mới phải resolve key theo locale được chọn và hiển thị tiếng Anh.

Nếu ứng dụng **lưu chuỗi đã dịch** vào `flowScope` lúc bước 1, chuỗi đó có thể tiếp tục xuất hiện bằng tiếng Việt ở bước 4. Ưu tiên lưu **code + dữ liệu nghiệp vụ**, hoặc để `MessageContext` quản lý resolver theo semantics của Web Flow, rồi xác minh hành vi qua redirect và khi locale đổi.

Tài liệu SWF nói `MessageContext` giữ message qua redirect, nhưng điều đó **không cam kết mọi implementation sẽ dịch lại đã-resolve message khi đổi locale**. Trong test cần quan sát kết quả thực tế và quyết định có làm mới, clear hoặc tạo lại message theo request ngôn ngữ mới hay không.

### 13.3. Locale không đồng nghĩa múi giờ

`vi-VN` có thể là locale, còn `Asia/Ho_Chi_Minh` là time zone. Ngày tham gia là `LocalDate`, thời điểm thanh toán có thể là `Instant` hoặc `ZonedDateTime`. Nếu message có ngày/giờ động, phải biết giá trị đang là ngày lịch hay thời điểm tuyệt đối, format cho đúng locale **và** timezone.

Đừng lấy ngày đã format để quyết định điều kiện nghiệp vụ; validation nên dùng object ngày/giờ đã được chuyển kiểu. Chỉ ở bước render mới đổi giá trị thành chuỗi phù hợp người dùng.

### 13.4. Fallback cho mã xác nhận sau khi flow kết thúc

Nếu người dùng xác nhận thành công, rồi execution kết thúc, việc quay lại URL cũ có thể không còn `MessageContext`. Do đó:

- Trang kết quả ngay sau flow có thể render mã `booking.confirmed` với confirmation code.
- Với biên lai xem lại sau này, server đọc booking từ database và **tạo message theo locale của request hiện tại**.
- Không lưu nguyên văn “Đã xác nhận...” như dữ liệu nghiệp vụ dài hạn; lưu mã/loại trạng thái và các giá trị cần thiết.

Điều này cũng giúp người dùng xem lại một booking bằng ngôn ngữ mới sau khi flow đã kết thúc.

## 14. Thiết kế nội dung dự phòng có trách nhiệm

`defaultText` có ích nhưng nên có **quy tắc sử dụng rõ ràng**. Mục tiêu là không để người dùng gặp key kỹ thuật hoặc trang lỗi trắng khi một bản dịch bị thiếu.

| Loại thông báo | Default text nên làm gì? | Ví dụ |
| --- | --- | --- |
| Validation field | Chỉ cách sửa dữ liệu, không yêu cầu kiến thức kỹ thuật | “Vui lòng nhập ngày tham gia.” |
| Hết chỗ/giá đổi | Giải thích điều vừa thay đổi và hành động tiếp theo | “Dịch vụ đã hết chỗ, hãy chọn lại.” |
| Thành công | Nêu kết quả đã được xác nhận, tránh tiết lộ dữ liệu dư | “Đặt chỗ đã được xác nhận.” |
| Lỗi hệ thống | Câu chung, có bước phục hồi | “Không thể hoàn tất. Hãy thử lại.” |
| Từ chối quyền | Không tiết lộ thông tin của tài nguyên khác | “Bạn không có quyền thực hiện thao tác.” |

### 14.1. Ba mức fallback nên thiết kế

1. **Bản dịch cụ thể** cho thông báo/field.
2. **Bản dịch chung** nếu nội dung có thể dùng lại an toàn.
3. **Default text** ngắn gọn, không rò chi tiết kỹ thuật.

Như vậy, khi thiếu `booking.visitDate.required` vẫn có thể dùng `booking.form.required` để người dùng hiểu nguyên nhân, trước khi tới câu mặc định.

### 14.2. Không lạm dụng fallback

Nếu mọi message đều có `defaultText` tiếng Việt, bản tiếng Anh có thể âm thầm hiển thị lẫn hai ngôn ngữ khi thiếu key. Vì vậy:

- Bổ sung kiểm thử hoặc công cụ so khớp key để tìm bản dịch thiếu.
- Ghi nhận missing code ở mức **observability**, không đưa raw key/stack trace ra UI.
- Định nghĩa ngôn ngữ mặc định của sản phẩm rõ ràng, nhất quán giữa Boot global bundle và flow bundle.
- Với thao tác quan trọng như thanh toán, quyền hoặc thông báo pháp lý, không coi một câu dự phòng quá chung là thay thế bản dịch đã được kiểm duyệt.

Không nên dùng `useCodeAsDefaultMessage=true` như một chiến lược UX production; chế độ này phù hợp để phát hiện key thiếu trong phát triển.

## 15. Những lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân thường gặp | Bước kiểm tra |
| --- | --- | --- |
| UI hiển thị `booking.confirmed` thay vì câu chữ | Thiếu key, message source trả code | Bundle, mã được gọi, cấu hình fallback |
| UI chỉ hiển thị `???key???` hoặc lỗi lookup | Không có key/default, view resolver xử lý thiếu message | MessageSource và view engine |
| Bản tiếng Việt không được dùng | Locale request sai, file đặt sai tên, source không nạp | `LocaleResolver`, `messages_vi.properties`, classpath |
| Một số thông báo nằm tiếng Anh dù `vi-VN` | Key thiếu ở vi, fallback sang root bundle | So khớp key hai bundle |
| `{0}` hiện nguyên văn | Message chưa được format hoặc không có argument | `MessageBuilder.arg`, pattern và source |
| Thứ tự dịch vụ/số lượng bị hoán đổi | Dịch sai vị trí `{0}`/`{1}` | Argument contract và test |
| Dấu nháy đơn bị mất/hiển thị sai | `MessageFormat` diễn giải `'` | Escape dấu nháy, `alwaysUseMessageFormat` |
| Lỗi trường ngày không dùng key riêng | Model short name/property không khớp | Code thực tế của `typeMismatch` |
| Đổi ngôn ngữ nhưng message cũ vẫn bằng tiếng Việt | Đã lưu sẵn chuỗi vào scope hoặc message snapshot | Locale mỗi request và lúc resolve |
| Form bị lỗi nhưng không có thông báo | View không render `MessageContext`/`BindingResult` | View adapter, source field, HTML render |
| Thông báo success xuất hiện khi transaction lỗi | Message được phát quá sớm | Chỉ phát success sau commit xác định |
| Lỗi xuất hiện lặp nhiều lần khi Back | Thêm message nhiều lần mà không dọn theo vòng đời | Điểm tạo message, messageContext lifecycle |
| File tiếng Việt hiển thị lỗi dấu | Sai encoding giữa file/bundle/runtime | UTF-8, Spring message source encoding |
| Thông báo lỗi tiết lộ mã bí mật | Cho dữ liệu nhạy cảm vào arguments/log | Chính sách dữ liệu, output encoding |

### 15.1. Cách chẩn đoán có thứ tự

Với hiện tượng **chỉ thấy key thô**:

1. Ghi code được action/validator tạo và locale ở request đó.
2. Kiểm tra chính xác file bundle đã được đóng gói vào classpath cạnh flow XML hoặc trong basename global.
3. Xác nhận key không bị sai chữ hoa/thường, dấu chấm, prefix hoặc model short name.
4. Kiểm tra message source thực sự được view/flow sử dụng và fallback hierarchy.
5. Gọi `MessageSource.getMessage` trực tiếp trong unit test với cùng code/args/locale.
6. Kiểm tra HTML sau render nếu unit test tra message đúng nhưng UI vẫn sai.

Với hiện tượng **mã đúng nhưng tham số sai**, tập trung vào `arg`/`resolvableArg`, thứ tự `{0}`/`{1}`, `MessageFormat` và locale. Với hiện tượng **field error không hiện**, kiểm tra `source` và view integration trước khi thay nội dung properties.

## 16. Bộ kiểm thử tối thiểu cho mã, tham số và fallback

### 16.1. Unit test Spring MessageSource với hai locale

Ví dụ JUnit Jupiter với `ResourceBundleMessageSource`, giả định các file trong phần 7 được đặt ở `src/main/resources/flows/booking/`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.context.NoSuchMessageException;
import org.springframework.context.support.ResourceBundleMessageSource;

class BookingMessagesTest {
    private ResourceBundleMessageSource source() {
        ResourceBundleMessageSource source = new ResourceBundleMessageSource();
        source.setBasename("flows/booking/messages");
        source.setDefaultEncoding("UTF-8");
        source.setFallbackToSystemLocale(false);
        return source;
    }

    @Test
    void vietnameseBundleUsesArgument() {
        String text = source().getMessage(
            "booking.remaining", new Object[] {2},
            Locale.forLanguageTag("vi-VN"));

        assertEquals("Chỉ còn 2 chỗ.", text);
    }

    @Test
    void englishUsesDefaultBundle() {
        String text = source().getMessage(
            "booking.confirmed", new Object[] {"BK-001"}, Locale.US);

        assertEquals("Reservation BK-001 was confirmed.", text);
    }

    @Test
    void unknownCodeCanHaveExplicitFallback() {
        String text = source().getMessage(
            "booking.future.key", null,
            "Thông báo đang được cập nhật.",
            Locale.forLanguageTag("vi-VN"));

        assertEquals("Thông báo đang được cập nhật.", text);
    }

    @Test
    void unknownCodeWithoutFallbackIsAnError() {
        assertThrows(NoSuchMessageException.class, () ->
            source().getMessage("booking.unknown", null, Locale.US));
    }
}
~~~

Test tiếng Anh dùng bundle mặc định vì ví dụ `messages_en.properties` là tùy chọn; nếu tạo file en có cùng key, kiểm chứng nội dung thật theo source. Những unit test này chứng minh **Spring MessageSource** tra được code và format arguments; chúng **không tự chứng minh Web Flow đã nối đúng message source**.

### 16.2. Test riêng MessageBuilder và MessageContext

Tạo một `DefaultMessageContext` với `MessageSource` đã chuẩn bị; ghi resolver bằng:

~~~java
MessageContext messages = new DefaultMessageContext(source);

messages.addMessage(new MessageBuilder()
    .error()
    .source("visitDate")
    .code("booking.visitDate.required")
    .defaultText("Vui lòng nhập ngày tham gia.")
    .build());

assertTrue(messages.hasErrorMessages());
assertEquals(1, messages.getMessagesBySource("visitDate").length);
~~~

Đoạn test giả định có import của `MessageContext`, `DefaultMessageContext`, `MessageBuilder` và một biến `source` kiểu `MessageSource`. Nếu cần kiểm chứng **text đã resolve** theo locale, hãy dùng đúng locale context/test infrastructure của phiên bản SWF đang dùng; không chỉ nhìn số lượng message rồi kết luận đã dịch đúng.

### 16.3. Test tích hợp theo state và locale

| ID | Bối cảnh | Thao tác | Kỳ vọng |
| --- | --- | --- | --- |
| M01 | `vi-VN`, thiếu `visitDate` | Event `next` | Ở lại form, hiển thị câu tiếng Việt |
| M02 | `en-US`, thiếu `visitDate` | Event `next` | Cùng code, câu tiếng Anh |
| M03 | `vi-VN`, ngày sai kiểu | POST `visitDate=abc` | Thông báo `typeMismatch` cụ thể theo field |
| M04 | Thiếu key riêng nhưng có key chung | Ghi message bằng `codes` | Hiển thị nội dung chung có tên field |
| M05 | Không có cả hai key | Ghi message có `defaultText` | Câu dự phòng được hiển thị |
| M06 | Không có key và không có fallback | Test lookup | Phát hiện lỗi rõ ràng, không âm thầm bỏ qua |
| M07 | Hai arguments | Thử `booking.capacity.limit` | Số khách và tên dịch vụ đúng vị trí |
| M08 | `resolvableArg` | Dùng `booking.field.visitDate` | Dịch tên field, không in raw code |
| M09 | Message có dấu nháy | Resolve pattern `It''s...` | Không mất dấu nháy và tham số |
| M10 | Chuyển state có redirect | Ghi lỗi/thông báo rồi render | Message đến view đích đúng theo flow |
| M11 | Back sau lỗi validation | Quay lại view | Không lặp vô hạn thông báo cũ |
| M12 | Đổi locale giữa execution | `vi-VN` rồi `en-US` | Nội dung theo chính sách locale mới |
| M13 | Hai flow khác nhau trong một session | Gây lỗi ở flow A | Flow B không nhận message riêng của A |
| M14 | Flow timeout | Gửi execution URL cũ | Không làm lộ message/dữ liệu của người khác |
| M15 | Validation thất bại | Bấm `confirm` | Không commit nghiệp vụ |
| M16 | Service báo hết chỗ | Phát `booking.slot.unavailable` | Cảnh báo có bước chọn lại |
| M17 | Commit thành công | Phát `booking.confirmed` sau commit | Mã booking đúng, không báo success sai |
| M18 | Bản dịch không có dấu tiếng Việt đúng | Test resources UTF-8 | Không có ký tự lỗi encoding |
| M19 | Form lỗi + global banner cùng lúc | Render view | Cả lỗi field và message global đều hiện |
| M20 | Truy cập lại biên lai sau flow kết thúc | GET receipt có quyền | Tạo nội dung theo locale hiện tại từ DB |

### 16.4. Chia lớp test

**Unit test** kiểm tra code/arguments/defaultText và bundle cho từng locale. **Flow test** xác minh validator action tạo message, giữ đúng state và tồn tại qua redirect. **MVC integration test** kiểm tra `LocaleResolver`, view resolver, HTML và binding errors. **Service test** bảo đảm success chỉ phát khi transaction đã commit, còn lỗi nghiệp vụ trả đúng code và không để lại dữ liệu ghi dở.

Đừng coi việc một code resolve đúng trong unit test là bằng chứng giao diện sẽ hiển thị đúng khi `MessageContext` đang dùng một message source khác.

## 17. Bài tập và đáp án

### Bài A — chọn `arg` hay `resolvableArg`

Cho message:

~~~properties
booking.form.required=Trường {0} là bắt buộc.
booking.field.visitDate=ngày tham gia
~~~

**Yêu cầu:** Viết `MessageBuilder` dùng key chung để hiển thị “Trường ngày tham gia là bắt buộc.”

**Gợi ý đáp án:**

~~~java
new MessageBuilder()
    .error()
    .source("visitDate")
    .code("booking.form.required")
    .resolvableArg("booking.field.visitDate")
    .defaultText("Vui lòng nhập ngày tham gia.")
    .build();
~~~

Nếu thay `resolvableArg` bằng `arg` với cùng chuỗi, output có thể chứa literal `booking.field.visitDate` thay vì tên field đã dịch.

### Bài B — thiết kế mã chung và riêng

Một form có `visitDate`, `email` và `numberOfGuests`. Hãy định nghĩa mã thông báo cho lỗi thiếu dữ liệu của từng field, một mã tổng quát, bản dịch tiếng Việt/Anh và nội dung dự phòng. Với lỗi số khách nhỏ hơn 1, phải dùng code validation riêng thay vì `typeMismatch` vì kiểu số vẫn parse được.

**Tiêu chí đạt:** có danh sách code rõ ràng, argument contract nếu có `{0}`, field source đúng tên, fallback theo thứ tự và test cho cả hai locale.

### Bài C — thiếu bản dịch tiếng Việt

Trong `messages.properties` có `booking.slot.unavailable` nhưng trong `messages_vi.properties` không có. Locale của request là `vi-VN`.

**Trả lời:** hệ thống có thể lấy câu từ bundle gốc tiếng Anh, tùy hierarchy message source và thứ tự lookup. Viết test chứng minh hành vi thực tế, sau đó bổ sung bản dịch tiếng Việt; không chấp nhận “chắc chắn sẽ dùng câu tiếng Anh” khi chưa kiểm tra cấu hình.

### Bài D — chuyển ngôn ngữ khi flow đang dở

Người dùng ở `details`, nhập sai ngày, nhận lỗi tiếng Việt; sau đó chuyển ngôn ngữ sang tiếng Anh và bấm `next` một lần nữa.

**Yêu cầu:** giải thích vì sao lưu **code và dữ liệu** có lợi hơn lưu nguyên văn câu đã dịch vào `flowScope`; viết test cho request trước/sau đổi locale. Cần phân biệt message đã được resolve ở execution snapshot với việc tạo message mới trong request mới.

### Bài E — tìm lỗi trong properties

~~~properties
booking.confirmed=It's confirmed: {0}
booking.capacity.limit=Đã đăng ký {1} khách cho {0}.
~~~

**Yêu cầu:** rà soát dấu nháy `'` khi chạy `MessageFormat`, kiểm tra thứ tự `{0}`/`{1}` so với mã Java gọi, và thêm unit test để thấy output thật. Không thay dữ liệu bằng cách nối chuỗi trực tiếp trong controller.

## 18. Checklist khi đưa message code vào production

- [ ] Mỗi lỗi nghiệp vụ có **mã ổn định**, không phụ thuộc ngôn ngữ.
- [ ] Mã được đặt theo feature và ngữ nghĩa, không dùng một `error` chung cho mọi tình huống.
- [ ] `source` của lỗi field khớp property trong model/binder.
- [ ] Mức `info`/`warning`/`error` phù hợp hậu quả và cách khắc phục.
- [ ] `codes` đặt từ cụ thể đến tổng quát; `defaultText` có nội dung có thể hiểu.
- [ ] Có `messages.properties` mặc định và bundle cho các locale được hỗ trợ.
- [ ] Spring Boot global messages và flow-specific messages được kiểm tra precedence rõ.
- [ ] Mọi placeholder `{0}`/`{1}` có argument contract và test parse/format.
- [ ] Tên field được dịch bằng `resolvableArg` khi dùng thông báo chung.
- [ ] Test `MessageFormat` với dấu nháy, số, locale và format ngày/giờ.
- [ ] Lỗi `typeMismatch` dùng key đúng theo model short name/property thật.
- [ ] View hiển thị cả lỗi field lẫn thông báo global.
- [ ] Redirect, back, đổi locale và session expiration không làm sai nội dung.
- [ ] Không lưu chuỗi đã dịch thành dữ liệu nghiệp vụ lâu dài nếu còn cần đổi locale.
- [ ] Không có raw code, stack trace, secret hoặc thông tin cá nhân quá mức trong UI/log.
- [ ] Message success chỉ phát sau khi trạng thái nghiệp vụ đã được xác nhận.
- [ ] Có automated test phát hiện key thiếu và hồi quy của bundle tiếng Việt/Anh.

## 19. Tài liệu tham khảo chính thức

1. [Spring Web Flow 3.x Reference — Working with Messages](https://docs.spring.io/spring-webflow/docs/3.0.x/reference/) — mục **13.12**, bao gồm `MessageContext`, plain/internationalized messages, bundle theo flow và key `typeMismatch`.
2. [Spring Web Flow — MessageBuilder Javadoc](https://docs.spring.io/spring-webflow/docs/3.0.1/api/org/springframework/binding/message/MessageBuilder.html) — `code`, `codes`, `arg`, `resolvableArg`, `defaultText`, `source` và mức độ.
3. [Spring Web Flow — MessageContext Javadoc](https://docs.spring.io/spring-webflow/docs/3.0.1/api/org/springframework/binding/message/MessageContext.html) — quản lý và truy vấn message trong flow.
4. [Spring Framework — MessageSource API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/MessageSource.html) — tra code, arguments, locale, default message và `NoSuchMessageException`.
5. [Spring Framework — ApplicationContext internationalization](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html) — `MessageSource`, `ResourceBundleMessageSource` và parent context.
6. [Spring Boot — Internationalization](https://docs.spring.io/spring-boot/reference/features/internationalization.html) — cấu hình `spring.messages.basename`, root bundle và fallback.
7. [Spring MVC — Locale](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/localeresolver.html) — `LocaleResolver`, `LocaleChangeInterceptor` và thông tin time zone.
8. [Java SE — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html) — cú pháp `{0}`, định dạng số/ngày và dấu nháy.

**Điểm cần nhớ:** Trong Spring Web Flow, logic ghi **mã thông báo và tham số**, `MessageSource` chọn **bản dịch theo locale**, còn `defaultText` giúp có nội dung **dự phòng** nếu tra mã không thành công. Hãy thiết kế thứ tự key cụ thể → key chung → fallback, kiểm thử cả bundle và giao diện thực tế, đồng thời giữ các thông báo nghiệp vụ nhất quán với state, validation, redirect và kết quả transaction.
