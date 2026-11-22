# Loại bỏ resource không được tham chiếu

Email HTML có thể sử dụng hình ảnh logo, banner, biểu đồ hoặc biểu tượng được nhúng trực tiếp trong thư. Với **Spring Framework Mail**, các tài nguyên này thường được thêm bằng `MimeMessageHelper.addInline(...)` và được HTML tham chiếu thông qua URL dạng `cid:...`. Khi template có nhiều nhánh điều kiện, không phải tài nguyên nào cũng xuất hiện trong HTML đã render. Nếu ứng dụng vẫn thêm tất cả resource có thể dùng, email sẽ mang theo những MIME part không được nội dung tham chiếu.

**Loại bỏ resource không được tham chiếu** nghĩa là chỉ đưa vào MIME message những inline resource có Content-ID thực sự được sử dụng trong HTML cuối cùng. Điều này giúp giảm kích thước thư, tránh hiển thị các ảnh thừa như attachment, hạn chế phát tán dữ liệu không cần thiết và làm cho cấu trúc MIME phản ánh đúng nội dung được render.

Bài học trình bày quan hệ giữa HTML CID và MIME Content-ID, cách phát hiện resource thừa hoặc bị thiếu, cách lọc resource trước khi gọi `addInline`, cách xử lý template có điều kiện và CSS, cùng ví dụ Spring Boot, kiểm thử và các lỗi thường gặp.

## 1. Inline resource được liên kết với HTML như thế nào?

Giả sử email có logo:

```html
<html>
  <body>
    <img src="cid:company-logo" alt="Logo công ty">
    <h1>Xin chào!</h1>
  </body>
</html>
```

HTML không chứa byte của ảnh. Nó chỉ tham chiếu tới một MIME part bằng Content-ID. Khi tạo thư, ứng dụng thêm ảnh:

```java
helper.addInline(
    "company-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);
```

Trong MIME, part ảnh có thể có các header tương tự:

```text
Content-Type: image/png
Content-ID: <company-logo>
Content-Disposition: inline
Content-Transfer-Encoding: base64

[IMAGE_DATA]
```

Hai định danh cần khớp:

| HTML | MIME / Spring |
|---|---|
| `src="cid:company-logo"` | `Content-ID: <company-logo>` |
| URI scheme `cid:` | `helper.addInline("company-logo", ...)` |
| Tham chiếu tài nguyên | MIME part chứa byte của tài nguyên |

`cid:company-logo` là tham chiếu tới part có Content-ID tương ứng. Nó không phải tên file, đường dẫn trên máy chủ hay Message-ID của toàn bộ email.

Nếu HTML không tham chiếu `company-logo` nhưng ứng dụng vẫn gọi `addInline("company-logo", ...)`, MIME message có thể chứa một part ảnh không được nội dung sử dụng. Tùy mail client, part đó có thể bị bỏ qua, được hiển thị trong danh sách attachment hoặc làm thư lớn hơn mà không mang lại giá trị cho người nhận.

## 2. Resource nào được xem là không được tham chiếu?

Giả sử template có thể dùng ba ảnh:

- `brand-logo`: logo luôn hiển thị.
- `promotion-banner`: chỉ hiển thị khi chiến dịch có banner.
- `order-chart`: chỉ hiển thị trong email báo cáo.

Danh sách resource ứng dụng chuẩn bị:

```text
brand-logo
promotion-banner
order-chart
```

HTML sau render của một email xác nhận đơn hàng có thể chỉ chứa:

```html
<img src="cid:brand-logo" alt="Logo">
<h1>Đơn hàng đã được xác nhận</h1>
```

Khi đó:
- `brand-logo` được tham chiếu: cần thêm vào MIME.
- `promotion-banner` không được tham chiếu: bỏ qua.
- `order-chart` không được tham chiếu: bỏ qua.

Tập resource cần đính kèm là **giao của tập CID được HTML tham chiếu và tập resource ứng dụng có thể cung cấp**.

Gọi:
- `R` là tập Content-ID được tìm thấy trong HTML đã render;
- `A` là tập Content-ID có trong danh sách asset do ứng dụng chuẩn bị.

Khi đó:

```text
Inline resources to add = R ∩ A
Unused candidates       = A - R
Missing resources       = R - A
```

Ba kết quả có ý nghĩa khác nhau:

| Kết quả | Ý nghĩa | Cách xử lý |
|---|---|---|
| `R ∩ A` | HTML tham chiếu và ứng dụng có resource | Thêm resource vào MIME. |
| `A - R` | Resource được chuẩn bị nhưng HTML không dùng | Loại khỏi message. |
| `R - A` | HTML tham chiếu CID nhưng không có resource | Báo lỗi render/build email hoặc dùng fallback được thiết kế trước. |

Không nên âm thầm bỏ qua CID bị thiếu. Nếu HTML vẫn chứa `cid:promotion-banner` nhưng không có part tương ứng, người nhận có thể thấy ảnh lỗi. Đó là lỗi tính nhất quán giữa template và tài nguyên, cần được phát hiện trước khi gửi.

## 3. Vì sao cần loại bỏ inline resource thừa?

### 3.1. Giảm kích thước email

Ảnh được nhúng trong MIME thường được mã hóa Base64. Payload có thể tăng khoảng một phần ba so với byte gốc, chưa kể MIME header và boundary. Nếu template có nhiều banner hoặc biểu đồ nhưng chỉ dùng một ảnh, việc thêm tất cả làm tăng dung lượng thư không cần thiết.

Kích thước lớn có thể:
- vượt giới hạn message của SMTP provider;
- làm thời gian truyền lâu hơn;
- tăng bộ nhớ cần thiết khi dựng MIME;
- khiến email client tải hoặc xử lý thư chậm hơn.

### 3.2. Tránh resource thừa xuất hiện như attachment

Một số mail client hiển thị các MIME part không được HTML tham chiếu như tệp đính kèm. Người nhận có thể thấy những ảnh không liên quan hoặc nghĩ rằng email có thêm tài liệu.

`addInline` xác định disposition và Content-ID cho resource, nhưng không bảo đảm mọi client đều ẩn part không được tham chiếu.

### 3.3. Không gửi dữ liệu không cần thiết

Một resource không được tham chiếu có thể chứa:
- hình ảnh nội bộ;
- biểu đồ có số liệu;
- metadata ảnh;
- nội dung được tạo riêng cho một nhánh template;
- dữ liệu mà người nhận không cần biết.

Dù part không hiển thị trong body, byte của nó vẫn được gửi tới SMTP relay và có thể được lưu trong mailbox hoặc hệ thống xử lý thư. Vì vậy, loại resource thừa còn là một bước **giảm thiểu dữ liệu**.

### 3.4. Giữ cấu trúc MIME khớp với nội dung

Một email có một ảnh logo thì MIME nên có part logo tương ứng. Một email không có banner thì không cần part banner. Sự nhất quán này giúp việc đọc raw MIME, kiểm tra CID và chẩn đoán lỗi đơn giản hơn.

### 3.5. Tránh công việc tạo resource không cần thiết

Nếu biểu đồ chỉ dành cho email báo cáo nhưng service tạo biểu đồ cho mọi loại email, CPU và RAM vẫn bị tiêu tốn dù ảnh không được dùng. Có thể lọc sớm trước khi tạo byte array, ngoài bước lọc cuối dựa trên HTML đã render.

## 4. Phân biệt inline resource và attachment thông thường

Không phải mọi file trong email đều cần được tham chiếu bởi HTML.

| Loại MIME part | API Spring | Cách được sử dụng | Có lọc theo CID HTML không? |
|---|---|---|---|
| Inline image | `addInline(...)` | HTML tham chiếu `cid:...` | Có. |
| Attachment PDF | `addAttachment(...)` | Người nhận mở/tải file độc lập | Không. |
| Attachment CSV | `addAttachment(...)` | Người nhận mở dữ liệu | Không. |
| Plain text body | `setText(...)` | Nội dung thay thế hoặc nội dung thư | Không. |
| HTML body | `setText(...)` | Nội dung HTML | Là nguồn để tìm CID. |

**Chỉ loại bỏ inline resource không được tham chiếu.** Không xóa PDF hoặc CSV chỉ vì chúng không xuất hiện trong HTML; attachment độc lập có mục đích riêng và có thể được yêu cầu rõ ràng trong email.

Nếu email có cả inline image và attachment:
- phân tích CID trong HTML;
- chọn đúng inline resources;
- gọi `setText(...)`;
- thêm inline resources được chọn bằng `addInline(...)`;
- thêm các attachment độc lập bằng `addAttachment(...)`;
- gửi sau khi hoàn thiện MIME.

## 5. Vì sao nên lọc trước khi gọi addInline?

`MimeMessageHelper` có API thêm inline resource, ví dụ:

```java
helper.addInline("brand-logo", logoResource, "image/png");
```

Không nên giả định helper cung cấp một API công khai tương đương `removeInline(...)` để xóa từng resource đã thêm. Khi đã tạo MIME part, việc xóa trực tiếp phụ thuộc cấu trúc multipart và có thể làm sai quan hệ giữa body và resource.

Cách đơn giản, dễ kiểm soát là:
1. Render HTML hoàn chỉnh.
2. Thu thập CID được HTML tham chiếu.
3. Đối chiếu với registry resource do ứng dụng cung cấp.
4. Báo lỗi nếu thiếu resource.
5. Chỉ gọi `addInline` cho các resource được tham chiếu.
6. Tạo/gửi MIME message sau khi đã có danh sách đã lọc.

```text
Render HTML
    |
    v
Find cid: references
    |
    v
Compare with asset registry
    |
    +--> CID missing -> fail / fallback
    |
    v
Select referenced assets only
    |
    v
Create MimeMessageHelper
    |
    v
setText(...)
    |
    v
addInline(selected assets)
    |
    v
addAttachment(independent files)
    |
    v
send(...)
```

Nếu code hiện tại đã gọi `addInline` cho mọi asset rồi mới phát hiện resource thừa, phương án an toàn thường là **tạo một MimeMessage mới từ HTML và danh sách resource đã lọc**. Chỉ nên sửa multipart tree trực tiếp khi ứng dụng tự quản lý cấu trúc MIME và có kiểm thử tương ứng.

## 6. Xác định CID được tham chiếu trong HTML

CID có thể xuất hiện ở nhiều vị trí, không chỉ `img[src]`.

Các vị trí thường gặp:
- `<img src="cid:logo">`;
- thuộc tính `background="cid:background-image"` trong HTML email cũ;
- CSS inline như `style="background-image:url('cid:banner')"`;
- CSS trong thẻ `<style>`, nếu email client mục tiêu hỗ trợ kiểu hiển thị đó;
- các thuộc tính tài nguyên khác mà ứng dụng chủ động cho phép.

Ví dụ:

```html
<img src="cid:brand-logo" alt="Logo">

<table background="cid:mail-background">
  <tr>
    <td style="background-image:url('cid:promo-banner')">
      Nội dung khuyến mãi
    </td>
  </tr>
</table>
```

Khi thu thập CID, phải hiểu **các vị trí HTML/CSS mà ứng dụng thực sự sử dụng**. Một regex tìm mọi chuỗi `cid:` trong toàn bộ HTML có thể nhận nhầm nội dung văn bản, comment hoặc ví dụ code thành resource được dùng.

Một chiến lược tốt:
- dùng HTML parser để duyệt các phần tử và thuộc tính;
- phân tích các thuộc tính URL như `src`, `background`, `poster` nếu template cho phép;
- phân tích `style` và các thẻ `style` nếu có CSS CID;
- xử lý `srcset` riêng nếu ứng dụng dùng CID trong `srcset`;
- bỏ qua URL HTTP/HTTPS vì đó là tài nguyên ngoài, không phải inline MIME part;
- chuẩn hóa CID theo một quy ước do ứng dụng kiểm soát.

## 7. Quy ước Content-ID nhất quán

Nên tạo CID từ các token ổn định, đơn giản do server định nghĩa:

```text
brand-logo
promotion-banner
order-chart
footer-icon
```

HTML:

```html
<img src="cid:brand-logo" alt="Logo">
```

Java:

```java
helper.addInline(
    "brand-logo",
    logoResource,
    "image/png"
);
```

Không đưa dấu ngoặc nhọn MIME vào URL HTML. Trong HTML dùng `cid:brand-logo`; `MimeMessageHelper` tạo Content-ID cho MIME part theo API.

### 7.1. Tránh trùng CID

Một message không nên có nhiều inline resource khác nhau cùng một Content-ID. Nếu registry chứa hai asset cùng CID, hãy báo lỗi trước khi gửi.

Một CID được tham chiếu nhiều lần trong HTML thường chỉ cần **một MIME part**:

```html
<img src="cid:brand-logo" alt="Logo đầu trang">
<img src="cid:brand-logo" alt="Logo chân trang">
```

Chỉ thêm một lần `brand-logo`; cả hai vị trí có thể tham chiếu cùng part.

### 7.2. Phân biệt CID và tên resource

File `mail/logo-company.png` có thể dùng CID `brand-logo`:

```java
helper.addInline(
    "brand-logo",
    new ClassPathResource("mail/logo-company.png"),
    "image/png"
);
```

Tên file, CID và Content-Type là ba giá trị riêng:
- tên file xác định nơi lấy resource;
- CID liên kết HTML với MIME part;
- Content-Type mô tả kiểu dữ liệu.

Không tự suy ra CID từ filename nếu template dùng một tên khác.

### 7.3. URI CID và mã hóa

Trong ứng dụng, nên giới hạn CID vào một tập ký tự an toàn, ví dụ chữ, số, dấu chấm, gạch dưới và gạch ngang. Như vậy việc ánh xạ `cid:...` sang key trong registry đơn giản và ít lỗi.

Đặc tả URI CID có thể biểu diễn một số ký tự bằng percent-encoding. Nếu hệ thống cần CID có ký tự đặc biệt hoặc địa chỉ dạng `local-part@domain`, hãy dùng một parser/normalizer tuân theo quy tắc CID URI phù hợp; không áp dụng một regex đơn giản rồi giả định xử lý được mọi trường hợp. **Trong ví dụ bài học, CID được kiểm soát theo quy ước ASCII đơn giản**.

Không tự lowercase toàn bộ Content-ID nếu quy ước hoặc hệ thống hiện tại phân biệt chữ hoa/thường ở phần định danh. Hãy dùng một canonicalization rule thống nhất cho cả template và registry.

## 8. Ví dụ registry và selector cho inline resource

Ta có thể mô hình hóa resource bằng một record:

```java
package com.example.mail;

import org.springframework.core.io.InputStreamSource;

public record InlineAsset(
    String contentId,
    InputStreamSource resource,
    String contentType
) {}
```

Một kết quả render chứa HTML và danh sách resource có thể dùng:

```java
package com.example.mail;

import java.util.List;

public record RenderedEmail(
    String plainText,
    String htmlText,
    List<InlineAsset> inlineAssets
) {}
```

`inlineAssets` là danh sách **candidate assets** cho template. Nó chưa có nghĩa tất cả đều phải được thêm vào MIME. Selector sẽ đối chiếu với CID trong HTML.

### 8.1. Dùng HTML parser thay vì tìm chuỗi tùy tiện

Có thể dùng Jsoup trong module xử lý email hoặc test:

```groovy
dependencies {
    implementation 'org.jsoup:jsoup:<approved-version>'
}
```

`<approved-version>` là placeholder; chọn bản được dự án phê duyệt. HTML parser cho phép duyệt thuộc tính của phần tử thay vì tìm kiếm text thô.

Ví dụ selector sau hỗ trợ CID ở `src`, `background`, `poster`, CSS inline và thẻ `style`. Nó dùng quy ước CID đơn giản chỉ gồm chữ, số, dấu chấm, gạch dưới và gạch ngang:

```java
package com.example.mail;

import java.util.LinkedHashSet;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;

public class InlineCidExtractor {

    private static final Pattern CID_ATTRIBUTE =
        Pattern.compile("^cid:([a-zA-Z0-9._-]+)$",
            Pattern.CASE_INSENSITIVE);

    private static final Pattern CSS_CID =
        Pattern.compile(
            "url\\\\(\\\\s*['\\\\"]?cid:([a-zA-Z0-9._-]+)['\\\\"]?\\\\s*\\\\)",
            Pattern.CASE_INSENSITIVE
        );

    public Set<String> extract(String html) {
        Document document = Jsoup.parseBodyFragment(html);
        Set<String> contentIds = new LinkedHashSet<>();

        for (Element element : document.getAllElements()) {
            collectAttribute(element.attr("src"), contentIds);
            collectAttribute(element.attr("background"), contentIds);
            collectAttribute(element.attr("poster"), contentIds);
            collectCss(element.attr("style"), contentIds);
        }

        for (Element style : document.select("style")) {
            collectCss(style.data(), contentIds);
        }

        return contentIds;
    }

    private static void collectAttribute(
            String value, Set<String> contentIds) {

        if (value == null || value.isBlank()) {
            return;
        }

        String candidate = value.trim();
        if (!candidate.regionMatches(true, 0, "cid:", 0, 4)) {
            return;
        }

        Matcher matcher = CID_ATTRIBUTE.matcher(candidate);
        if (!matcher.matches()) {
            throw new IllegalArgumentException(
                "CID URI không hợp lệ: " + candidate
            );
        }

        contentIds.add(matcher.group(1));
    }

    private static void collectCss(
            String css, Set<String> contentIds) {

        if (css == null || css.isBlank()) {
            return;
        }

        Matcher matcher = CSS_CID.matcher(css);
        while (matcher.find()) {
            contentIds.add(matcher.group(1));
        }
    }
}
```

Selector là ví dụ cho tập cú pháp template được hỗ trợ, không phải một HTML/CSS parser đầy đủ cho mọi email:
- Nếu dùng `srcset`, cần phân tích danh sách candidate URL riêng.
- Nếu CSS được tạo từ stylesheet ngoài hoặc có cú pháp phức tạp, cần mở rộng parser phù hợp.
- Nếu ứng dụng cho phép CID trong thuộc tính khác, phải thêm thuộc tính đó vào policy.
- Nếu HTML chứa `cid:` trong text hoặc comment, selector không coi đó là tài nguyên được tham chiếu.
- Nếu dùng CID URI có percent-encoding hoặc ký tự ngoài allowlist, cần thay normalizer đơn giản bằng implementation phù hợp.

Không dùng regex trên toàn bộ HTML để thay thế parser; regex ở đây chỉ xử lý phần giá trị CSS `url(...)` sau khi đã lấy từ đúng ngữ cảnh CSS.

### 8.2. Đối chiếu với registry và loại resource thừa

```java
package com.example.mail;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class InlineAssetSelector {

    private final InlineCidExtractor extractor;

    public InlineAssetSelector(InlineCidExtractor extractor) {
        this.extractor = extractor;
    }

    public List<InlineAsset> select(
            String html,
            List<InlineAsset> candidates) {

        Set<String> referenced = extractor.extract(html);

        Map<String, InlineAsset> registry = new LinkedHashMap<>();
        for (InlineAsset asset : candidates) {
            InlineAsset previous =
                registry.putIfAbsent(asset.contentId(), asset);

            if (previous != null) {
                throw new IllegalArgumentException(
                    "Content-ID bị trùng: " + asset.contentId()
                );
            }
        }

        // HTML tham chiếu CID không có resource tương ứng:
        // đây là lỗi template/asset, không gửi một thư bị hỏng.
        List<String> missing = referenced.stream()
            .filter(cid -> !registry.containsKey(cid))
            .toList();

        if (!missing.isEmpty()) {
            throw new IllegalStateException(
                "Thiếu inline resource cho CID: " + missing
            );
        }

        // Giữ thứ tự xuất hiện đầu tiên trong HTML, thêm mỗi CID một lần.
        List<InlineAsset> selected = new ArrayList<>();
        for (String cid : referenced) {
            selected.add(registry.get(cid));
        }

        return List.copyOf(selected);
    }
}
```

Kết quả:
- Các CID được HTML tham chiếu được chọn.
- CID trùng trong danh sách candidate bị từ chối.
- CID có trong HTML nhưng không có resource bị báo lỗi.
- Candidate không được HTML tham chiếu không xuất hiện trong danh sách kết quả.
- Một CID xuất hiện nhiều lần trong HTML chỉ được thêm một lần do dùng `Set`.

Trong ứng dụng thật, có thể ghi metric số candidate, số selected và số unused. Không ghi nội dung ảnh hoặc dữ liệu nhạy cảm để chẩn đoán.

## 9. Tích hợp selector với JavaMailSender

Ví dụ service nhận một `RenderedEmail`, chọn inline resources trước rồi mới xây MIME message:

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.util.List;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class HtmlMailService {

    private final JavaMailSender mailSender;
    private final InlineAssetSelector assetSelector;

    public HtmlMailService(
            JavaMailSender mailSender,
            InlineAssetSelector assetSelector) {
        this.mailSender = mailSender;
        this.assetSelector = assetSelector;
    }

    public void send(
            String recipient,
            String subject,
            RenderedEmail rendered) throws MessagingException {

        // 1. Chọn đúng resource mà HTML thực sự tham chiếu.
        List<InlineAsset> selected = assetSelector.select(
            rendered.htmlText(),
            rendered.inlineAssets()
        );

        // 2. Chỉ tạo MIME sau khi đã xác định danh sách hợp lệ.
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_RELATED,
            "UTF-8"
        );

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject(subject);

        // 3. Tạo body trước khi thêm inline resources.
        helper.setText(
            rendered.plainText(),
            rendered.htmlText()
        );

        // 4. Chỉ thêm các CID được tham chiếu.
        for (InlineAsset asset : selected) {
            helper.addInline(
                asset.contentId(),
                asset.resource(),
                asset.contentType()
            );
        }

        // 5. Gửi sau khi hoàn thiện MIME.
        mailSender.send(message);
    }
}
```

`MULTIPART_MODE_RELATED` phù hợp với HTML có các tài nguyên inline liên quan. Nếu email còn có attachment độc lập như PDF, có thể chọn mode `MULTIPART_MODE_MIXED_RELATED` và gọi `addAttachment` riêng sau khi thiết lập body/inline theo cấu trúc phù hợp.

**Thứ tự quan trọng:** `setText(...)` trước `addInline(...)`. Selector chỉ quyết định resource nào được thêm; nó không thay thế thứ tự xây MIME body.

### 9.1. Tại sao chọn resource trước khi tạo MimeMessage?

Việc chọn trước có một số lợi ích:
- nếu thiếu CID, lỗi xảy ra trước khi gửi;
- không tạo MIME part rồi tìm cách xóa;
- có thể đo số asset được chọn trước khi dựng message;
- dễ kiểm thử selector độc lập với SMTP;
- giảm nguy cơ message bị gửi với HTML tham chiếu tới resource không tồn tại.

Nếu resource được tạo tốn kém, tốt hơn nữa là chỉ **tạo byte của asset sau khi biết nó được dùng**. Ví dụ, đừng vẽ biểu đồ 2 MB nếu HTML render không có thẻ tham chiếu biểu đồ.

## 10. Template có điều kiện và resource thừa

Giả sử template có logo, banner và biểu đồ:

```html
<img src="cid:brand-logo" alt="Logo">

<div th:if="¤{showPromotion}">
  <img src="cid:promotion-banner" alt="Ưu đãi">
</div>

<div th:if="¤{showChart}">
  <img src="cid:order-chart" alt="Biểu đồ đơn hàng">
</div>
```

Khi render:
- `showPromotion=false` thì HTML không còn CID `promotion-banner`.
- `showChart=true` thì HTML có CID `order-chart`.
- `brand-logo` luôn được tham chiếu.

Danh sách candidate có thể gồm cả ba resource, nhưng selector chỉ trả:
```text
brand-logo
order-chart
```

Banner bị loại vì không có trong HTML kết quả.

### 10.1. Giữ điều kiện template và registry đồng bộ

Có hai cách tổ chức:

**Cách A — Registry chứa tất cả asset có thể dùng.** Render HTML trước, selector tìm CID rồi lọc registry. Cách này thuận tiện khi số asset nhỏ và resource có thể mở lazy.

**Cách B — Renderer chỉ đăng ký asset theo nhánh đã chọn.** Khi `showPromotion` đúng, renderer thêm banner vào danh sách; khi sai, không thêm. Sau đó vẫn có thể chạy selector để bảo đảm HTML và registry khớp.

Cách B giảm công việc tạo candidate không cần thiết. Tuy nhiên, nếu điều kiện trong Java và điều kiện trong template được viết tách rời, chúng có thể lệch nhau. Hãy dùng cùng một model/decision để quyết định cả HTML lẫn registry.

### 10.2. Chỉ tạo byte sau khi xác nhận cần dùng

Thay vì render biểu đồ trước mọi email:

```java
List<InlineAsset> assets = new ArrayList<>();

if (showChart) {
    byte[] chartBytes = chartRenderer.render(reportData);
    assets.add(new InlineAsset(
        "order-chart",
        new ByteArrayResource(chartBytes),
        "image/png"
    ));
}
```

Nếu `showChart` sai, ứng dụng không tạo biểu đồ. Selector vẫn hữu ích để kiểm tra lần cuối vì HTML template có thể bị thay đổi hoặc có nhánh điều kiện khác.

## 11. CSS và các tham chiếu CID không nằm trong img[src]

Không phải tất cả inline resource đều xuất hiện trong `<img>`. Một số template email dùng:

```html
<td style="background-image:url('cid:mail-background')">
  Nội dung
</td>
```

Hoặc:

```html
<style>
  .hero {
    background-image: url("cid:hero-banner");
  }
</style>
```

Nếu extractor chỉ quét `img[src]`, nó sẽ không thấy hai CID này và có thể bỏ nhầm resource cần thiết.

Có ba chiến lược:
1. **Hạn chế cú pháp template:** chỉ cho phép CID trong `img[src]`, đơn giản hóa extractor.
2. **Hỗ trợ CSS CID có chủ đích:** parse `style` attribute và thẻ `style`, đồng thời kiểm tra mail client có hỗ trợ cách hiển thị đó.
3. **Dùng asset registry được tạo cùng template model:** template/renderer trả ra danh sách asset được sử dụng, nhưng cần kiểm tra consistency với HTML đầu ra.

Nếu sử dụng CSS ngoài, `srcset` hoặc thuộc tính đặc biệt của email client, hãy ghi rõ chúng trong contract của template và thêm test. Đừng giả định một extractor chỉ quét `src` là đủ cho mọi kiểu HTML.

### 11.1. srcset

Ví dụ:

```html
<img
  src="cid:logo-small"
  srcset="cid:logo-small 1x, cid:logo-large 2x"
  alt="Logo">
```

Nếu ứng dụng dùng CID trong `srcset`, phải phân tích từng candidate URL trong thuộc tính này. Chỉ lấy `src` sẽ bỏ sót `logo-large`; bỏ sót resource có thể khiến client chọn ảnh 2x nhưng không tìm thấy MIME part.

Nếu email client mục tiêu không hỗ trợ cách dùng này hoặc ứng dụng không cần ảnh responsive CID, hãy giới hạn template vào một `src` đơn giản. Một cú pháp được hỗ trợ rõ ràng thường dễ bảo trì hơn một extractor cố đoán mọi HTML.

## 12. Xử lý CID bị thiếu và asset không còn hợp lệ

Có hai dạng mismatch:

### 12.1. HTML tham chiếu nhưng registry không có asset

Ví dụ HTML có `cid:brand-logo` nhưng registry chỉ có `footer-icon`.

Đây là lỗi cần được phát hiện:
- template có thể dùng sai tên CID;
- asset bị quên đăng ký;
- điều kiện render không đồng bộ;
- resource không tải được hoặc bị loại bởi một bước trước đó.

Chọn một trong các hành vi có chủ đích:
- **Fail before send:** phù hợp với logo hoặc ảnh bắt buộc.
- **Render fallback:** bỏ thẻ ảnh hoặc thay bằng text khi ảnh tùy chọn.
- **Re-render:** nếu asset có thể được lấy lại từ nguồn tin cậy, tạo lại HTML/registry rồi kiểm tra lần nữa.

Không gửi nguyên HTML với CID bị thiếu nếu hình ảnh là thành phần quan trọng của thông điệp.

### 12.2. Registry có asset nhưng HTML không dùng

Đây là candidate thừa. Không thêm nó vào MIME. Nếu resource chưa được đọc, bỏ qua mà không cần tải byte.

Nếu resource đã được tạo:
- bỏ tham chiếu khỏi danh sách được gửi;
- giải phóng buffer/handle nếu có thể;
- không lưu byte thừa trong cache dài hạn nếu không cần;
- ghi metric tổng candidate và selected để phát hiện template hoặc renderer chuẩn bị quá nhiều asset.

### 12.3. File bị xóa hoặc lỗi sau khi selector chọn

Resource có thể tồn tại trong registry nhưng mở stream thất bại lúc Jakarta Mail đọc nó. Cần xử lý như lỗi tạo MIME, không giả định selector đã chứng minh byte có thể đọc.

Đối với resource quan trọng:
- dùng nguồn có thể mở stream mới;
- kiểm tra resource tồn tại trước khi tạo message nếu thích hợp;
- xử lý exception từ `addInline` hoặc `send`;
- không gửi message có body tham chiếu ảnh nhưng resource không thể đọc.

## 13. Nguồn resource có thể đọc lại được

`MimeMessageHelper.addInline(...)` nhận `InputStreamSource`. Nguồn nên cung cấp stream mới mỗi lần được đọc, đặc biệt khi quá trình tạo và gửi MIME cần truy cập nội dung hơn một lần.

Các nguồn thường phù hợp:
- `ClassPathResource` cho ảnh tĩnh trong JAR;
- `ByteArrayResource` cho byte array đã tạo;
- `FileSystemResource` cho file có thể mở lại;
- `InputStreamSource` tùy biến có factory mở stream mới.

Tránh một nguồn trả cùng một `InputStream` đã tiêu thụ:

```java
InputStream input = storage.openStream(assetId);
InputStreamSource oneShot = () -> input;
```

Thay vào đó:

```java
InputStreamSource repeatable =
    () -> storage.openNewStream(assetId);
```

`storage.openNewStream` là API minh họa; mỗi lần gọi cần trả một stream mới từ đầu. Nếu dữ liệu nhỏ, `ByteArrayResource` đơn giản hơn. Nếu dữ liệu lớn, có thể dùng storage có thể mở lại và kiểm soát vòng đời.

## 14. Kiểm thử selector và MIME

Kiểm thử nên bao gồm cả việc chọn CID lẫn kết quả MIME sau khi thêm resource.

### 14.1. Test loại resource không được tham chiếu

Giả sử HTML chỉ dùng `brand-logo` nhưng candidate có logo, banner và chart:

```java
@Test
void selectsOnlyReferencedInlineAssets() {
    String html = """
        <html><body>
          <img src="cid:brand-logo" alt="Logo">
        </body></html>
        """;

    List<InlineAsset> candidates = List.of(
        asset("brand-logo"),
        asset("promotion-banner"),
        asset("order-chart")
    );

    List<InlineAsset> selected =
        selector.select(html, candidates);

    assertThat(selected)
        .extracting(InlineAsset::contentId)
        .containsExactly("brand-logo");
}
```

`asset(...)` là fixture test tạo resource nhỏ, không phải method có sẵn trong Spring.

### 14.2. Test CID xuất hiện nhiều lần

```java
@Test
void addsOneAssetForRepeatedCidReferences() {
    String html = """
        <img src="cid:brand-logo">
        <img src="cid:brand-logo">
        """;

    List<InlineAsset> selected =
        selector.select(html, List.of(asset("brand-logo")));

    assertThat(selected).hasSize(1);
}
```

Một MIME part có thể được nhiều vị trí trong HTML tham chiếu.

### 14.3. Test CID bị thiếu

```java
@Test
void failsWhenHtmlReferencesUnknownCid() {
    String html = "<img src=\\"cid:missing-logo\\">";

    assertThatThrownBy(() ->
        selector.select(html, List.of(asset("brand-logo")))
    ).isInstanceOf(IllegalStateException.class);
}
```

Test này đảm bảo ứng dụng không âm thầm gửi email có ảnh bị hỏng.

### 14.4. Test CSS reference

```java
@Test
void detectsCidInInlineCss() {
    String html = """
        <div style="background-image:url('cid:hero-banner')">
          Hello
        </div>
        """;

    List<InlineAsset> selected =
        selector.select(html, List.of(asset("hero-banner")));

    assertThat(selected)
        .extracting(InlineAsset::contentId)
        .containsExactly("hero-banner");
}
```

Nếu ứng dụng dùng `srcset` hoặc CSS stylesheet phức tạp, cần có test riêng cho từng cú pháp được hỗ trợ.

### 14.5. Test MIME không chứa part thừa

Sau khi selector trả danh sách đã lọc, tạo `MimeMessage`, gọi `setText` rồi thêm các resource được chọn. Trong test, lưu thay đổi MIME và duyệt multipart để xác nhận:
- có đúng số inline part;
- mỗi part có Content-ID tương ứng;
- không có CID của candidate thừa;
- byte part trích xuất khớp byte fixture;
- HTML có CID nào thì MIME có part tương ứng.

Không chỉ assert số part nếu message còn có `multipart/alternative` hoặc attachment độc lập. Hãy duyệt cấu trúc MIME theo đúng nesting và phân biệt inline part với attachment.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Email có ảnh không xuất hiện trong HTML nhưng lại nằm trong attachment list | Thêm mọi candidate asset | Lọc theo CID trong HTML đã render. |
| HTML có `cid:logo` nhưng ảnh không hiện | Không có MIME part tương ứng hoặc CID khác nhau | So sánh URI CID và Content-ID. |
| Banner biến mất khi một điều kiện false | Extractor không nhận ra CSS/attribute tham chiếu | Hỗ trợ đúng cú pháp được dùng hoặc giới hạn template. |
| Ảnh hiển thị trong body nhưng vẫn có part thừa | Cùng lúc thêm candidate không dùng | Chỉ add selected resources; kiểm tra raw MIME. |
| Email lớn bất thường | Gắn tất cả ảnh có thể dùng hoặc ảnh quá lớn | Lọc asset, tạo lazy, resize/optimize. |
| CID trùng nhau | Registry có hai resource cùng ID | Từ chối duplicate CID trước khi tạo message. |
| HTML tham chiếu CID nhưng không có asset | Template và registry không đồng bộ | Fail before send hoặc render fallback. |
| Ảnh chỉ lỗi ở một nhánh template | Asset list không theo điều kiện render | Dùng chung model điều kiện và selector trên HTML cuối. |
| CSS background bị thiếu | Chỉ quét `img[src]` | Quét CSS CID nếu template/client hỗ trợ. |
| Ảnh 2x không hiện | CID trong `srcset` không được thu thập | Parse từng candidate srcset hoặc không dùng CID ở đó. |
| Resource được chọn nhưng lỗi khi gửi | Stream không mở lại được hoặc storage lỗi | Dùng repeatable InputStreamSource, xử lý lỗi đọc. |
| Thư vẫn có ảnh dù template không dùng | Đã thêm part trước khi lọc | Chọn resource trước khi addInline; tạo message mới nếu cần. |

## 16. Hiệu năng và quan sát vận hành

Có thể theo dõi một số số liệu không nhạy cảm:
- số candidate inline assets được renderer cung cấp;
- số CID thực sự được HTML tham chiếu;
- số resource bị loại;
- số CID thiếu;
- tổng byte của selected assets;
- thời gian tạo asset và dựng MIME;
- số lần lỗi mở resource.

Ví dụ log:

```text
mail_template=order-confirmation
inline_candidates=4
inline_referenced=2
inline_selected=2
inline_unused=2
mime_build_status=success
```

Không log byte ảnh, Base64 hoặc nội dung HTML có dữ liệu cá nhân/token. CID thường không phải bí mật, nhưng vẫn nên dùng identifier kỹ thuật không chứa thông tin cá nhân.

Nếu `inline_unused` luôn cao, có thể renderer đang tạo quá nhiều resource hoặc template có nhiều nhánh tùy chọn. Hãy tối ưu tạo asset theo điều kiện để tránh chi phí CPU/RAM trước cả khi selector loại bỏ chúng.

Với nhiều worker gửi đồng thời:
- giới hạn số ảnh tạo trong mỗi email;
- giới hạn tổng dung lượng MIME;
- không chia sẻ mutable `MimeMessage` hoặc `MimeMessageHelper` giữa các thread;
- tạo message riêng cho từng lần gửi;
- cache resource tĩnh nếu an toàn, nhưng không cache asset chứa dữ liệu riêng tư giữa các người nhận.

## 17. Bài tập thực hành

### Bài 1 — Chọn đúng resource

HTML có `cid:logo` và `cid:chart`. Registry có `logo`, `chart`, `banner`. Hãy xác định tập được thêm và tập bị loại.

**Gợi ý:** thêm `logo` và `chart`; loại `banner`.

### Bài 2 — Phát hiện CID bị thiếu

HTML tham chiếu `cid:promotion` nhưng registry không có CID đó. Hãy chọn hành vi phù hợp cho banner tùy chọn và logo bắt buộc. Viết test xác nhận lỗi hoặc fallback theo từng trường hợp.

### Bài 3 — CID lặp lại

Một HTML dùng cùng logo ở header và footer. Hãy chứng minh selector chỉ trả một asset và MIME chỉ cần một part có Content-ID đó.

### Bài 4 — CSS background

Template dùng `background-image:url('cid:hero')`. Hãy mở rộng extractor để nhận CSS CID, thêm test cho dấu nháy đơn, dấu nháy kép và khoảng trắng.

### Bài 5 — srcset

HTML có hai candidate `cid:small-logo` và `cid:large-logo` trong `srcset`. Hãy quyết định ứng dụng có hỗ trợ cú pháp này không. Nếu có, phân tích từng URL; nếu không, sửa contract template để chỉ dùng `src`.

### Bài 6 — Không tạo asset khi không cần

Một biểu đồ mất 300 ms để tạo và chỉ được dùng trong email báo cáo. Hãy đưa quyết định `showChart` vào renderer để tránh tạo byte khi email không phải báo cáo, sau đó vẫn dùng selector để kiểm tra CID/registry.

### Bài 7 — Phân biệt attachment

Email có `cid:logo` và file `invoice.pdf` được đính kèm độc lập. Hãy loại banner không dùng mà vẫn giữ PDF dù PDF không xuất hiện trong HTML. Giải thích tại sao chỉ inline resources được lọc theo CID.

### Bài 8 — Kiểm tra raw MIME

Tạo một message có hai inline candidate nhưng HTML chỉ tham chiếu một. Hãy lưu MIME trong test và xác nhận part của resource không được tham chiếu không tồn tại.

## 18. Tổng kết

Trong Spring Framework Mail, `MimeMessageHelper.addInline(...)` thêm một MIME part có Content-ID để HTML tham chiếu bằng `cid:...`. Nếu template có nhiều nhánh hoặc registry chứa nhiều asset có thể dùng, không nên thêm tất cả resource vào mọi email.

Hãy **render HTML trước, thu thập các CID thực sự được tham chiếu, đối chiếu với registry, báo lỗi nếu thiếu và chỉ gọi `addInline` cho resource được chọn**. Dùng HTML parser để xử lý đúng các thuộc tính/CSS mà template hỗ trợ, giữ CID duy nhất, bảo đảm resource có thể mở stream và kiểm tra MIME trong test. Chỉ lọc inline resource; attachment độc lập vẫn được giữ theo yêu cầu nghiệp vụ.

Cách làm này giảm dung lượng, tránh gửi dữ liệu không cần thiết và giữ MIME message nhất quán với nội dung người nhận thực sự thấy.
