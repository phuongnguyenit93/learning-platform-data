# Tách mẫu câu đầy đủ và cung cấp ngữ cảnh cho bản dịch

## 1. Vấn đề: bản dịch không phải là phép thay từng từ

Trong Java localization, việc tách một câu thành các mảnh nhỏ rồi nối lại ở runtime thường có vẻ thuận tiện:

```java
// Không nên dùng làm thiết kế cho nội dung đa ngôn ngữ
String message = prefix + count + suffix;
```

Nhưng câu trong ngôn ngữ tự nhiên có **trật tự từ, số nhiều, giống ngữ pháp, cách xưng hô và ngữ cảnh**. Không có bảo đảm rằng mọi ngôn ngữ đều đặt số đếm ở giữa đúng hai mảnh giống tiếng Anh. Một từ ngắn cũng có thể có nhiều nghĩa: `Open` là nút “Mở”, nhưng `Open` ở trạng thái cửa hàng lại là “Đang mở cửa”; `Save` là lệnh lưu, còn trong một ngữ cảnh khác có thể nói về tiết kiệm.

Nguyên tắc quan trọng:

> **Tách nguyên một thông điệp có nghĩa thành một đơn vị dịch**, chứa những placeholder có ngữ nghĩa rõ ràng. Hãy đưa cho người dịch đủ ngữ cảnh để họ có thể viết lại toàn bộ câu cho đúng ngôn ngữ đích.

Trong Java, một cách triển khai phổ biến là đặt câu đầy đủ trong `ResourceBundle` rồi dùng `MessageFormat` để chèn dữ liệu. Cách này cho phép bản dịch **đổi thứ tự placeholder**, thay cách diễn đạt và, khi cần, chọn các biến thể theo số lượng/ngữ pháp.

Bài này tập trung vào: **đơn vị thông điệp phải đủ nghĩa**, **tài liệu ngữ cảnh cho người dịch**, **hợp đồng placeholder**, **số nhiều và biến thể ngữ pháp**, và **kiểm thử bản dịch thực tế**.

## 2. Vì sao nối chuỗi làm mất khả năng dịch đúng?

### 2.1. Trật tự từ không cố định

Ví dụ ứng dụng có hai biến `customer` và `orderId`. Cách ghép mảnh:

```java
// Ví dụ phản diện: các fragment được giữ ở nhiều resource key
String text = bundle.getString("hello.prefix")
        + customer
        + bundle.getString("order.middle")
        + orderId
        + bundle.getString("order.suffix");
```

Cách này giả định người dịch bắt buộc giữ đúng thứ tự: mở đầu → tên người → đoạn giữa → mã đơn hàng → kết thúc. Nhưng bản dịch tiếng Việt có thể hợp lý hơn khi bắt đầu bằng **đơn hàng** rồi mới đến **tên khách hàng**. Người dịch không thể đổi thứ tự hai giá trị nếu chương trình đã cố định bằng phép nối.

Thay bằng **một thông điệp trọn nghĩa**:

```properties
# Messages_en.properties
order.ready=Hello {0}, order {1} is ready.
```

```properties
# Messages_vi.properties
order.ready=Đơn hàng {1} của {0} đã sẵn sàng.
```

Với cùng dữ liệu `{0} = "Lan"`, `{1} = "A-7"`, hai câu kết quả lần lượt là:

```text
Hello Lan, order A-7 is ready.
Đơn hàng A-7 của Lan đã sẵn sàng.
```

Sự khác biệt nằm hoàn toàn trong **mẫu câu**, không cần viết `if (locale...)` để hoán đổi các phần văn bản trong Java.

### 2.2. Số nhiều có thể thay đổi cả câu

Ví dụ tiếng Anh:

```text
You have 1 new message.
You have 3 new messages.
```

Nếu chỉ dịch riêng danh từ `message` và nối `s`, ứng dụng đã hard-code ngữ pháp tiếng Anh vào chương trình. Cách đó không phù hợp cho nhiều ngôn ngữ: một số cần nhiều nhóm số lượng; một số có cách chia từ hoặc thay đổi phần khác trong câu; một số không cần đổi danh từ theo số đếm như tiếng Anh.

Ngay cả trường hợp không có thông báo cũng có thể cần một **câu riêng**:

```text
You have no new messages.
Bạn không có thông báo mới.
```

Đừng coi `0`, `1` và “nhiều” chỉ là vài đuôi từ có thể dịch riêng. Chọn **mẫu câu đầy đủ** cho biến thể cần thiết.

### 2.3. Giống ngữ pháp, vai trò người tham gia và ngữ cảnh

Một thông báo có thể phụ thuộc người thực hiện hành động, đối tượng bị tác động hoặc danh từ đi kèm. Chẳng hạn nội dung dạng “{người A} đã mời {người B}” có thể có cấu trúc khác trong ngôn ngữ đích. Bản dịch cũng cần biết danh tính hiển thị của `{0}` là **tên người**, **mã**, **mốc thời gian**, hay **số lượng**.

**Không suy ra quy tắc giống ngữ pháp từ giới tính người dùng** một cách tùy tiện; chỉ sử dụng những thuộc tính mà dữ liệu nghiệp vụ thực sự cung cấp và ngôn ngữ đích cần. Với nhiều hệ thống, thiết kế câu trung tính, tránh phụ thuộc giống ngữ pháp sẽ dễ bản địa hóa hơn.

## 3. Xác định đúng đơn vị dịch

Một **translation unit** tốt là thông điệp có nghĩa trong một ngữ cảnh hiển thị cụ thể. Đó không nhất thiết luôn là một đoạn văn dài; nhãn độc lập như “Tìm kiếm” có thể là một đơn vị dịch. Nhưng **không được cắt một câu đang cần ngữ pháp thống nhất thành các mảnh tùy ý**.

| Thiết kế không nên dùng | Vì sao có vấn đề? | Thiết kế phù hợp hơn |
| --- | --- | --- |
| `"You have " + n + " new message" + pluralSuffix` | Đuôi số nhiều và thứ tự từ bị đóng đinh | Các mẫu câu `inbox.zero`, `inbox.one`, `inbox.other` theo chính sách ngôn ngữ |
| `"Hello " + name + ", order " + id + " is ready."` | Người dịch không đổi được trật tự tên và mã | `order.ready=Hello {0}, order {1} is ready.` |
| `"Open"` dùng cho mọi nơi | Không biết là hành động hay trạng thái | `file.action.open`, `store.status.open` |
| Ghép `"From"` + tên + `"to"` + tên | Có thể thay đổi trật tự/giới từ trong ngôn ngữ khác | Một thông điệp hoàn chỉnh có hai placeholder |
| Dịch riêng một từ rồi tái sử dụng ở tiêu đề, nút, tooltip | Cùng từ nguồn có thể có nghĩa khác nhau | Khóa và context phân biệt từng chức năng |

Nguyên tắc **“một đơn vị có nghĩa”** không có nghĩa phải lặp vô điều kiện cùng một câu ở hàng trăm nơi: khi hai vị trí có **cùng nghĩa, cùng vai trò, cùng ràng buộc giao diện**, có thể tái sử dụng một key. Nhưng nếu ngữ cảnh khác nhau, việc dùng chung chỉ vì câu tiếng Anh trông giống nhau dễ dẫn đến bản dịch sai.

## 4. Cung cấp ngữ cảnh gì cho người dịch?

Người dịch không nhìn thấy toàn bộ mã nguồn hoặc luồng nghiệp vụ. Một chuỗi như `Open`, `Pending`, `1 of 3` hay `{0} added {1}` **không đủ thông tin để dịch chính xác**. Nên gắn **translator context** với từng đơn vị dịch:

1. **Mục đích hiển thị:** nút bấm, tiêu đề, trạng thái, toast, email, thông báo xác nhận, trợ năng hay lỗi biểu mẫu?
2. **Vị trí và ảnh chụp giao diện:** màn hình nào, phần tử trước/sau là gì, ai là người đọc?
3. **Ý nghĩa nghiệp vụ:** “open” là “mở file” hay “đang hoạt động”? “charge” là tính phí hay sạc pin?
4. **Mô tả mọi placeholder:** `{0}` là tên người; `{1}` là mã đơn hàng; `{2}` là số tiền đã **được format**. Đừng chỉ ghi “arg 0, arg 1”.
5. **Loại dữ liệu và ví dụ:** số lượng `0/1/2/5`, mẫu tên dài, mã có dấu nối, ngày/giờ theo vùng, dữ liệu có ký tự đặc biệt.
6. **Biến thể ngữ pháp:** trường hợp số không, một, nhiều; role của người tham gia; giống ngữ pháp nếu sản phẩm thực sự quản lý được thông tin này.
7. **Ràng buộc giao diện:** chiều dài gợi ý, nhãn tối đa, khả năng xuống dòng, hỗ trợ RTL, có được viết tắt không?
8. **Định dạng/markup:** placeholder chứa văn bản thuần, liên kết, số tiền hay markup? Có ký tự đặc biệt của `MessageFormat` cần giữ nguyên không?
9. **Hành vi khi thiếu dịch:** fallback về ngôn ngữ nào? Nội dung ưu tiên dùng văn phong trang trọng hay thân mật?

Ví dụ một key với ngữ cảnh tốt:

```text
Key: order.ready
Source: Hello {0}, order {1} is ready.
Description: Thông báo xuất hiện sau khi đơn đặt hàng chuẩn bị xong.
{0}: displayName — tên hiển thị của khách, ví dụ "Lan".
{1}: orderId — mã đơn hàng, ví dụ "A-7", giữ nguyên.
Audience: người mua hàng.
Tone: ngắn gọn, lịch sự; có thể đảo thứ tự placeholder.
UI: có thể xuống dòng; không được xóa một trong hai placeholder.
Screenshot: ảnh của màn hình theo dõi đơn hàng trong hệ thống dịch.
```

Chú thích `#` trong file `.properties` có thể giúp người đọc file, nhưng **`ResourceBundle` không trả những comment đó qua `getString`**. Nền tảng quản lý bản dịch nên lưu context dưới dạng metadata riêng, file đi kèm hoặc comment được công cụ trích xuất bảo toàn. Đừng giả định mọi pipeline sẽ chuyển nguyên comment đến người dịch.

## 5. Đặt khóa theo nghĩa và ngữ cảnh, không theo nguyên văn tiếng Anh

Khóa resource nên ổn định khi thay đổi câu chữ:

```properties
order.ready=Hello {0}, order {1} is ready.
checkout.payment.failed=Payment failed. Please try again.
file.action.open=Open
store.status.open=Open
```

Hai key cuối có cùng bản tiếng Anh nhưng **ngữ cảnh dịch khác nhau**. Trong tiếng Việt, một số bản dịch phù hợp có thể là `Mở` và `Đang mở cửa`.

Nên tránh các khóa kiểu `YouHaveNewMessages`, `hello_prefix` hoặc khóa bằng nguyên chuỗi tiếng Anh nếu chúng khiến thay đổi copy đồng nghĩa với đổi API và khó duy trì context. Có thể nhóm key theo tính năng và loại thông điệp: `inbox.empty`, `inbox.count`, `order.ready`, `file.action.open`.

**Một khóa không nhất thiết tương đương một câu về mặt dấu chấm:** tiêu đề, CTA độc lập và aria-label vẫn là các đơn vị hoàn chỉnh theo chức năng. Tiêu chí là người dịch biết **mục đích và ngữ cảnh ngữ pháp** của đơn vị đó.

## 6. Ví dụ chạy được: một câu đầy đủ, thứ tự placeholder và số lượng

Ví dụ sau dùng Java 17+, `ResourceBundle` + `MessageFormat`. Nó minh họa:

- Mỗi biến thể số lượng được dịch bằng **một câu đầy đủ**, không nối tiền tố/hậu tố.
- Bản dịch có quyền **đổi thứ tự `{0}` và `{1}`**.
- Từ khóa và giá trị trong resource là một **hợp đồng** giữa mã và người dịch.

Tạo cấu trúc:

```text
workspace/
├── src/
│   └── demo/
│       └── MessageContextDemo.java
└── demo/
    ├── Messages.properties
    ├── Messages_en.properties
    └── Messages_vi.properties
```

**`demo/Messages.properties`** — fallback gốc bằng tiếng Anh:

```properties
inbox.zero=You have no new messages.
inbox.one=You have {0} new message.
inbox.other=You have {0} new messages.
order.ready=Hello {0}, order {1} is ready.
```

**`demo/Messages_en.properties`**:

```properties
# inbox.*: Thông báo số tin nhắn chưa đọc. {0}: số lượng nguyên không âm.
inbox.zero=You have no new messages.
inbox.one=You have {0} new message.
inbox.other=You have {0} new messages.
# order.ready: {0} là tên khách, {1} là mã đơn hàng.
order.ready=Hello {0}, order {1} is ready.
```

**`demo/Messages_vi.properties`**:

```properties
# inbox.*: Số thông báo mới. {0}: số lượng nguyên không âm.
inbox.zero=Bạn không có thông báo mới.
inbox.one=Bạn có {0} thông báo mới.
inbox.other=Bạn có {0} thông báo mới.
# order.ready: {0} là tên khách; {1} là mã đơn, được đảo thứ tự.
order.ready=Đơn hàng {1} của {0} đã sẵn sàng.
```

**`src/demo/MessageContextDemo.java`**:

```java
package demo;

import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class MessageContextDemo {
    private static final String BASE_NAME = "demo.Messages";

    private static final ResourceBundle.Control CONTROL =
            ResourceBundle.Control.getNoFallbackControl(
                    ResourceBundle.Control.FORMAT_PROPERTIES);

    private static String format(ResourceBundle bundle,
                                 Locale locale,
                                 String key,
                                 Object... arguments) {
        return new MessageFormat(bundle.getString(key), locale)
                .format(arguments);
    }

    private static void showCount(Locale locale, int count) {
        ResourceBundle bundle =
                ResourceBundle.getBundle(BASE_NAME, locale, CONTROL);

        // Chỉ là chính sách minh họa cho hai ngôn ngữ đã triển khai.
        String key = count == 0 ? "inbox.zero"
                : count == 1 ? "inbox.one"
                : "inbox.other";

        System.out.println(locale.toLanguageTag() + " | "
                + format(bundle, locale, key, count));
    }

    private static void showOrder(Locale locale) {
        ResourceBundle bundle =
                ResourceBundle.getBundle(BASE_NAME, locale, CONTROL);
        System.out.println(locale.toLanguageTag() + " | "
                + format(bundle, locale, "order.ready", "Lan", "A-7"));
    }

    public static void main(String[] args) {
        Locale english = Locale.forLanguageTag("en-US");
        Locale vietnamese = Locale.forLanguageTag("vi-VN");

        showCount(english, 0);
        showCount(english, 1);
        showCount(english, 3);
        showOrder(english);

        showCount(vietnamese, 0);
        showCount(vietnamese, 1);
        showCount(vietnamese, 3);
        showOrder(vietnamese);
    }
}
```

Từ thư mục `workspace`, chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 -d . src/demo/MessageContextDemo.java
java -cp . demo.MessageContextDemo
```

Đầu ra (terminal hiển thị UTF-8 đúng):

```text
en-US | You have no new messages.
en-US | You have 1 new message.
en-US | You have 3 new messages.
en-US | Hello Lan, order A-7 is ready.
vi-VN | Bạn không có thông báo mới.
vi-VN | Bạn có 1 thông báo mới.
vi-VN | Bạn có 3 thông báo mới.
vi-VN | Đơn hàng A-7 của Lan đã sẵn sàng.
```

### Vì sao ví dụ này đáng chú ý?

**Không có đoạn mã nào nối riêng “You have”, tên danh từ hay đuôi số nhiều.** Java chỉ chọn một **key ngữ nghĩa** rồi đưa dữ liệu vào câu đã dịch. Người dịch tiếng Việt thay cả câu `order.ready` để đưa mã đơn hàng lên trước tên khách, nhưng hợp đồng `{0}` và `{1}` vẫn giữ nguyên.

`ResourceBundle` sẽ tìm `Messages_en.properties` khi yêu cầu `en-US`, và `Messages_vi.properties` khi yêu cầu `vi-VN`. `getNoFallbackControl` bỏ nhánh thử default locale của JVM nhưng vẫn cho phép tài nguyên gốc; chính sách này giúp ví dụ ổn định. Tệp properties cần nằm trên runtime classpath đúng đường dẫn `demo/`.

**Giới hạn chủ ý:** điều kiện `count == 0 / 1 / other` chỉ để minh họa thông điệp **tiếng Anh và tiếng Việt trong bài**; đó **không phải thuật toán plural dùng chung cho tất cả ngôn ngữ**. Một số ngôn ngữ có nhiều loại số nhiều hoặc quy tắc xét số thập phân phức tạp. Với ứng dụng đa ngôn ngữ thật, phải dùng quy tắc plural của locale (ví dụ hệ thống dựa trên CLDR/ICU khi phù hợp), chứ không sao chép nhánh này cho mọi quốc gia.

## 7. Số nhiều: tách biến thể câu và chọn đúng quy tắc ngôn ngữ

Cần phân biệt hai việc:

1. **Chọn biến thể ngữ pháp** cho một số lượng/đại lượng cụ thể.
2. **Format số được in ra** cho locale đã chọn.

`NumberFormat` lo cách biểu diễn số, không tự quyết định toàn bộ ngữ pháp danh từ. `MessageFormat` tiêu chuẩn của `java.text` hỗ trợ các dạng như `number` và `choice`, nhưng nó **không phải engine CLDR plural hoàn chỉnh** với các nhãn `zero`, `one`, `two`, `few`, `many`, `other` áp dụng tự động cho mọi locale.

Ví dụ `ChoiceFormat` có thể chọn giữa những nhánh dựa trên ngưỡng số:

```java
// Trích đoạn minh họa: không phải quy tắc plural tổng quát.
String pattern = "{0,choice,0#No items|1#One item|1<Many items}";
String text = new MessageFormat(pattern, Locale.US)
        .format(new Object[] {3});
```

Kết quả `text` là `Many items`. Tuy nhiên, các ngưỡng đó chỉ diễn đạt một **chính sách cụ thể** của pattern, không thay thế quy tắc plural của tiếng Ả Rập, tiếng Nga, tiếng Ba Lan... và những ngôn ngữ khác.

Nếu sử dụng hệ thống có hỗ trợ **plural categories theo CLDR**, các nhãn `zero/one/two/few/many/other` phải được chọn **bởi quy tắc locale**, không được hiểu đơn giản `one` luôn là số bằng 1 hoặc `few` luôn là 2–4. Kể cả giá trị 0 đôi khi được thể hiện bằng `other` theo quy tắc của ngôn ngữ; một câu “Không có mục nào” vẫn có thể là **trường hợp nghiệp vụ riêng** được thiết kế tường minh.

### Vì sao phải giữ câu đầy đủ trong từng nhánh?

Không nên chỉ định nghĩa:

```text
singularSuffix=""
pluralSuffix="s"
```

Thay vào đó, dùng các đơn vị câu đầy đủ như `inbox.one` và `inbox.other` hoặc một thông điệp plural được công cụ l10n hỗ trợ. Người dịch có thể cần thay **động từ, cách, mạo từ, tính từ, vị trí số đếm và danh từ** cùng lúc. Hệ thống dịch cần cho xem toàn bộ các nhánh cạnh nhau và biết chúng sẽ hiển thị ở đâu.

## 8. Cung cấp hợp đồng placeholder rõ ràng

Placeholder là **biến số/ngữ nghĩa**, không phải văn bản được dịch tùy ý. Với Java `MessageFormat`, dạng phổ biến là `{0}`, `{1}`, `{2,number}`, `{3,date}`.

Ví dụ hợp đồng:

| Placeholder | Ý nghĩa | Kiểu dữ liệu | Ví dụ | Người dịch cần biết |
| --- | --- | --- | --- | --- |
| `{0}` | Tên hiển thị khách hàng | `String` | `Lan` | Có thể dài hoặc có dấu nháy; không được đổi nghĩa |
| `{1}` | Mã đơn hàng | `String` | `A-7` | Không dịch nội dung mã; có thể chuyển vị trí |
| `{2}` | Số lượng chưa đọc | `int` hoặc `Number` | `3` | Quy tắc plural cần xử lý riêng |
| `{3}` | Mốc thời gian | `Temporal/Date` theo API sử dụng | Ngày giao hàng | Chọn vùng giờ/lịch và mẫu định dạng phù hợp |

Trong `MessageFormat`, **thứ tự phần tử của `Object[]` phải giữ đúng hợp đồng** dù người dịch được quyền **đảo vị trí placeholder trong pattern**. Nếu nội dung tiếng Việt đặt `{1}` trước `{0}`, Java vẫn truyền tham số theo thứ tự ban đầu `{"Lan", "A-7"}`.

Không nên bảo người dịch “giữ nguyên vị trí placeholder”, vì điều đó phá mục tiêu thay đổi trật tự câu. Nên yêu cầu: **giữ nguyên tập placeholder, chỉ số và ý nghĩa**, cho phép đổi vị trí xuất hiện nếu câu cần; nếu cần lặp một tham số trong bản dịch thì phải xác định điều đó có hợp lệ với API không.

### Tên tham số có nghĩa và giới hạn của `MessageFormat`

Java `MessageFormat` chuẩn dùng **chỉ số** như `{0}`, không tự hỗ trợ `{customerName}` theo cú pháp placeholder có tên. Vì vậy một lớp dịch vụ có thể định nghĩa tên ngữ nghĩa trong mã/metadata rồi ánh xạ chúng sang chỉ số khi tạo `Object[]`. Với nền tảng l10n hỗ trợ placeholder đặt tên, vẫn cần hợp đồng rõ về kiểu và ý nghĩa.

Đừng tùy tiện trộn cú pháp ICU MessageFormat với `java.text.MessageFormat`; khả năng `plural` hoặc `select` của thư viện khác không mặc nhiên chạy được trong parser Java chuẩn. Chọn một engine, tài liệu hóa cú pháp và kiểm thử tất cả resource theo engine đó.

## 9. Cẩn trọng với `MessageFormat`, escape và dữ liệu động

Khi câu đầy đủ chứa dấu nháy đơn và dấu ngoặc nhọn, `MessageFormat` có quy tắc escape riêng:

- `{0}` là placeholder; muốn hiển thị chữ `{0}` như ký hiệu, dùng `'{0}'` trong pattern.
- `''` trong pattern in một dấu nháy đơn literal. Ví dụ pattern `It''s {0}.` mới có đầu ra `It's Lan.`.
- `'{'` và `'}'` lần lượt in ngoặc mở/đóng literal.
- Dấu nháy đơn mở quote nhưng không đóng có thể khiến placeholder bị in nguyên văn **mà không ném exception**.
- Dấu gạch chéo ngược là escape của Java source hoặc properties ở những tầng riêng; nó không tự thay thế cơ chế nháy đơn của `MessageFormat`.

Đối với văn bản **tham số** như `O'Brien` hoặc `{0}` nằm trong tên người, `MessageFormat` không phân tích lại nó như pattern thông thường. Đừng tự nhân đôi nháy đơn trong dữ liệu nhập rồi tạo ra tên hiển thị sai. Chỉ áp dụng quy tắc quote của `MessageFormat` cho **pattern**.

**Ranh giới an toàn:** hệ thống i18n không tự động ngăn XSS khi chuỗi kết quả được chèn vào HTML. Nếu ứng dụng web hiển thị thông điệp, hãy escape/encode theo **ngữ cảnh đầu ra** và dùng component/template API an toàn. Đừng coi người dịch hoặc placeholder là HTML đáng tin, đừng nối markup/URL không được kiểm soát vào câu; phần bôi đậm và liên kết nên được biểu diễn thành thành phần giao diện riêng hoặc cấu trúc được phép với ranh giới rõ ràng.

## 10. Ngữ cảnh cho người dịch khi có yếu tố ngữ pháp phức tạp

### 10.1. Đừng buộc người dịch suy ra giới tính hoặc vai trò

Ví dụ thông báo “{0} đã gửi {1} một lời mời” có hai người tham gia. Một ngôn ngữ đích có thể cần điều chỉnh từ ngữ theo người thực hiện hoặc người nhận. Nếu người dịch chỉ thấy `{0} invited {1}` mà không biết vai trò, họ dễ đổi sai hướng hành động.

Cần mô tả:

```text
{0}: người gửi lời mời (actor)
{1}: người nhận lời mời (recipient)
Người đọc: người nhận thông báo
Ngữ cảnh: thông báo hệ thống ngay sau hành động gửi thành công
```

Nếu sản phẩm không có dữ liệu ngữ pháp cần thiết, hãy cân nhắc một **câu trung tính** thay vì giả định giới tính hoặc tự suy từ tên người.

### 10.2. Không tái sử dụng cùng một từ giữa các ngữ cảnh khác nhau

Một nhãn `Archive` có thể là **hành động lưu trữ**, **danh mục hồ sơ**, hoặc **trạng thái đã lưu**. Ngay cả khi bản nguồn cùng một từ, bản dịch có thể khác về loại từ và sắc thái. Dùng key riêng cho từng nghĩa:

```properties
document.action.archive=Archive
navigation.archive=Archive
document.status.archived=Archived
```

Đừng dùng chung key chỉ để giảm số dòng resource. Điều quan trọng không phải tối thiểu hóa số key mà là **bảo toàn đúng ngữ nghĩa**.

### 10.3. Cẩn trọng với chiều dài và văn bản giao diện

Một câu đủ nghĩa có thể dài hơn bản tiếng Anh. Hãy cho phép giao diện xuống dòng hoặc co giãn phù hợp, kiểm thử trên mobile và các kích thước font/trợ năng. Nếu áp giới hạn ký tự, cần nói rõ đó là giới hạn cứng hay gợi ý; đừng bắt người dịch bỏ thông tin thiết yếu mà không có giải pháp thiết kế.

### 10.4. Tên riêng, số, ngày, tiền và đơn vị

Người dịch cần biết placeholder chứa **dữ liệu nguyên bản** hay **chuỗi đã được format**. Ví dụ:

- Mã đơn hàng và mã định danh: thường giữ nguyên, không dịch.
- Số tiền: dùng giá trị số + mã tiền theo dữ liệu nghiệp vụ; không tự quy đổi tiền tệ chỉ vì đổi locale.
- Ngày giờ: locale quyết định cách hiển thị, còn `ZoneId` là thông tin riêng.
- Số lượng: có thể cần một **giá trị số** để chọn nhánh plural, không chỉ chuỗi đã format.

Không cho người dịch sửa hoặc dịch các placeholder thành ký tự cố định trong câu. Thông điệp cần tương thích mọi giá trị hợp lệ của ứng dụng, không chỉ ảnh chụp mẫu.

## 11. Kiểm thử cả bản dịch và ngữ cảnh, không chỉ cú pháp

Bước kiểm tra lý tưởng có cả **kiểm thử tự động** lẫn **review ngôn ngữ trên giao diện**:

1. **Kiểm tra đầy đủ key:** mọi locale được cam kết hỗ trợ có các key cần thiết hoặc fallback được xác định rõ. Thiếu key có thể khiến `ResourceBundle` lấy chuỗi từ parent mà không báo lỗi.
2. **Kiểm tra placeholder:** bản dịch không làm mất `{0}`, `{1}` cần thiết, không nhầm chỉ số; cho phép thay thứ tự đúng ngữ pháp. Cần parser/hợp đồng phù hợp với engine, không chỉ đếm chuỗi bằng regex.
3. **Phân tích pattern:** thử tạo `MessageFormat` cho các mẫu; kiểm tra nháy đơn, ngoặc và subformat. Nhưng parser chấp nhận không chứng minh thông điệp đúng ý.
4. **Kiểm tra kết quả sau format:** dùng giá trị đại diện; so sánh cả câu đầy đủ trong các locale được triển khai.
5. **Kiểm tra trường hợp số lượng:** 0, 1, 2, 5, số lớn và nếu áp dụng cả số thập phân. Với thư viện plural theo CLDR, dùng bộ giá trị đại diện theo **locale** để chạm mọi category.
6. **Kiểm tra đổi thứ tự tham số:** bản dịch có thể in `{1}` trước `{0}`; dùng hai giá trị dễ phân biệt (ví dụ tên `Lan` và mã `A-7`) để phát hiện đổi nhầm.
7. **Kiểm tra ngữ cảnh hiển thị:** chụp ảnh có dữ liệu thật/giả lập, kiểm tra vị trí nút, tiêu đề, trạng thái, tiếng Việt có dấu, font, chiều rộng, màn hình nhỏ và trợ năng.
8. **Kiểm tra chuỗi có apostrophe:** `It's`, `don't`, tên `O'Brien`; phân biệt dấu nháy trong pattern với dữ liệu.
9. **Kiểm tra ngôn ngữ có ngữ pháp khác:** có cần variant khác theo vai trò, số lượng, giống ngữ pháp hoặc cách xưng hô? Đừng lấy tiếng Anh làm mô hình ngữ pháp duy nhất.
10. **Kiểm tra hợp đồng theo phiên bản:** khi thêm/sửa placeholder, thông báo cho đội dịch, cập nhật context và kiểm thử bản dịch cũ trước khi phát hành.

Một phép kiểm tra nhỏ trong Java có thể giúp khóa hợp đồng hai tham số:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class ContextContractTest {
    public static void main(String[] args) {
        String english =
                "Hello {0}, order {1} is ready.";
        String vietnamese =
                "Đơn hàng {1} của {0} đã sẵn sàng.";

        Object[] values = {"Lan", "A-7"};

        String en = new MessageFormat(english, Locale.US)
                .format(values);
        String vi = new MessageFormat(vietnamese,
                Locale.forLanguageTag("vi-VN"))
                .format(values);

        if (!en.equals("Hello Lan, order A-7 is ready.")) {
            throw new AssertionError(en);
        }
        if (!vi.equals("Đơn hàng A-7 của Lan đã sẵn sàng.")) {
            throw new AssertionError(vi);
        }
        System.out.println("2 context checks passed");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ContextContractTest.java
java -cp . ContextContractTest
```

Kết quả nếu hợp đồng và mẫu câu đúng:

```text
2 context checks passed
```

Đây là kiểm thử **hợp đồng** chứ không thể thay thế review chất lượng bản dịch; những câu sai ngữ pháp nhưng vẫn chứa đủ placeholder vẫn có thể vượt qua kiểm thử tự động.

## 12. Quy trình phối hợp giữa developer và người dịch

**Trước khi gửi bản nguồn cho người dịch:**

- Chọn key mang nghĩa nghiệp vụ, không dựa vào hình thức câu tiếng Anh.
- Thiết kế mỗi thông điệp là một **đơn vị hoàn chỉnh**; không tách thành mảnh chỉ để nối ở runtime.
- Với thông điệp có biến, viết context cho từng placeholder; cung cấp ảnh màn hình, ví dụ giá trị và những nhánh số lượng.
- Xác định engine thông điệp (`java.text.MessageFormat`, ICU hoặc cơ chế khác) và quy tắc escape tương ứng.
- Chọn chính sách fallback và danh sách locale mà sản phẩm thực sự hỗ trợ.

**Trong quá trình dịch:**

- Cho phép đổi trật tự placeholder nhưng yêu cầu giữ đúng **nghĩa/chỉ số/kiểu**.
- Không ép người dịch giữ nguyên số từ, cấu trúc câu, cách dùng dấu câu của bản tiếng Anh.
- Cung cấp công cụ xem preview theo locale với dữ liệu mẫu, kể cả 0, 1 và nhiều.
- Cho phép người dịch đặt câu hỏi hoặc phản hồi khi nội dung nguồn mơ hồ.

**Trước khi phát hành:**

- Kiểm tra cú pháp pattern và các placeholder với engine sẽ chạy ở production.
- Kiểm tra giá trị thực trên UI, giới hạn độ dài, khả năng xuống dòng, dấu tiếng Việt, RTL khi có, và trợ năng.
- Kiểm thử các ngữ cảnh dễ nhầm như “Open”, “Save”, nhãn trạng thái và thông báo có hai người tham gia.
- Đảm bảo mọi thay đổi ở hợp đồng placeholder đều đi cùng cập nhật bản dịch và tài liệu context.

## 13. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nối `prefix + count + suffix` | Khóa chặt trật tự câu, khó xử lý số nhiều | Dịch một mẫu câu đầy đủ và chọn nhánh theo locale |
| Dịch riêng “message” và thêm `s` | Đưa ngữ pháp tiếng Anh vào mọi ngôn ngữ | Dùng quy tắc plural đúng locale và câu đầy đủ |
| Dùng một key `open` cho mọi màn hình | Mơ hồ hành động/trạng thái | Key theo nghĩa, kèm mô tả/ảnh ngữ cảnh |
| Chỉ gửi `{0}`, `{1}` không giải thích | Người dịch nhầm tên người với số/mã | Hợp đồng placeholder có vai trò, kiểu và ví dụ |
| Yêu cầu giữ nguyên vị trí placeholder | Không thể đảo trật tự từ hợp ngữ pháp | Giữ **chỉ số và ý nghĩa**, cho phép thay thứ tự |
| Xem `0/1/other` là luật của mọi ngôn ngữ | Sai số nhiều với nhiều locale | Dùng dữ liệu plural theo ngôn ngữ, kiểm thử category |
| Cho người dịch nhận một từ không có ảnh hoặc ngữ cảnh | Từ có nhiều nghĩa bị dịch sai | Cung cấp screenshot, vị trí và hành động nghiệp vụ |
| Đưa nguyên HTML vào resource không kiểm soát | Lỗi layout hoặc rủi ro XSS | Dùng component an toàn và encode theo context |
| Dịch từng fragment nhưng kiểm thử chỉ câu tiếng Anh | Không phát hiện lỗi đảo vị trí/ngữ pháp | Kiểm thử toàn thông điệp ở mỗi locale |
| Chỉ kiểm tra `MessageFormat` không ném lỗi | Câu có thể sai nghĩa, mất placeholder do quote | So sánh output và review ngôn ngữ |
| Tưởng fallback có nghĩa bản dịch đã đủ | Một số câu rơi về ngôn ngữ gốc | Kiểm tra độ phủ key và theo dõi fallback |

## 14. Ghi nhớ

- **Đơn vị dịch nên là thông điệp trọn nghĩa.** Không ghép những mảnh văn bản cố định rồi hy vọng mọi ngôn ngữ đều có cùng ngữ pháp.
- **Placeholder phải có hợp đồng rõ ràng:** vị trí, ý nghĩa, kiểu dữ liệu, ví dụ và khả năng thay đổi thứ tự khi dịch.
- **Ngữ cảnh là một phần của chất lượng bản dịch:** ảnh giao diện, chức năng, đối tượng đọc, vai trò dữ liệu và phong cách cần được cung cấp cùng chuỗi nguồn.
- **Số nhiều và giống ngữ pháp không phải thao tác thêm hậu tố.** Khi cần, chọn các mẫu câu đầy đủ theo quy tắc locale hoặc dùng thư viện l10n hỗ trợ ngữ pháp tương ứng.
- **`ResourceBundle` tìm câu đã dịch; `MessageFormat` chèn dữ liệu.** Cả hai không tự quyết định câu có tự nhiên, đúng ngữ cảnh hay đúng văn hóa hay không; phải có review và kiểm thử.
