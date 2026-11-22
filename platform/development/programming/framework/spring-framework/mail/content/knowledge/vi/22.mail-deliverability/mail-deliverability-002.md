# SPF, DKIM và DMARC ở cấp miền

Một email gửi thành công qua `JavaMailSender` chưa chắc được hệ thống nhận đánh giá là hợp lệ. SMTP relay có thể đã chấp nhận thư, nhưng máy chủ đích vẫn cần kiểm tra xem IP gửi có được miền cho phép hay không, chữ ký của nội dung có hợp lệ hay không, và miền hiển thị trong địa chỉ `From` có phù hợp với các danh tính đã xác thực hay không.

Trong **Spring Framework Mail**, `JavaMailSender` chủ yếu xây dựng và gửi MIME message. Còn **SPF, DKIM và DMARC** là những cơ chế xác thực email **ở cấp miền và hạ tầng gửi**: bản ghi DNS, địa chỉ envelope sender, hệ thống ký DKIM, cấu hình SMTP provider và chính sách của domain. Chúng liên quan chặt chẽ đến deliverability, nhưng không phải ba thuộc tính mà chỉ cần bật trong `application.yml` là xong.

Bài học trình bày cách ba cơ chế phối hợp, phân biệt địa chỉ `From` trong nội dung với `MAIL FROM` của phiên SMTP, hiểu điều kiện **DMARC alignment**, cấu hình một miền gửi qua Spring Mail và nhà cung cấp SMTP, kiểm tra DNS/header, triển khai an toàn khi có nhiều hệ thống gửi thư, cùng các tình huống lỗi thực tế.

## 1. Ba cơ chế bảo vệ giải quyết ba câu hỏi khác nhau

| Cơ chế | Câu hỏi chính | Dữ liệu xác thực | Thành phần chủ yếu chịu trách nhiệm |
|---|---|---|---|
| **SPF** — Sender Policy Framework | IP của SMTP server đang gửi có được miền của envelope sender cho phép hay không? | IP gửi, `RFC5321.MailFrom` hoặc `HELO/EHLO` domain, SPF TXT record | DNS của miền và SMTP infrastructure |
| **DKIM** — DomainKeys Identified Mail | Những phần được ký của thông điệp có chữ ký mật mã hợp lệ do miền ký xác nhận không? | `DKIM-Signature`, khóa công khai DNS dưới selector | Outbound MTA/email provider hoặc DKIM signer |
| **DMARC** — Domain-based Message Authentication, Reporting & Conformance | Miền hiển thị trong `From` có được xác thực thông qua SPF hoặc DKIM **có alignment** không, và miền muốn receiver xử lý thất bại ra sao? | `RFC5322.From`, kết quả SPF/DKIM, TXT record `_dmarc` | DNS policy và receiving mail servers |

Tóm tắt:

- **SPF** cho phép miền công bố các hệ thống được quyền gửi bằng một SMTP envelope identity nhất định.
- **DKIM** cho phép kiểm tra chữ ký gắn với một signing domain và một phần nội dung/headers.
- **DMARC** gắn kết kết quả SPF/DKIM với **miền mà người nhận nhìn thấy ở From**.

Một email không cần **cả SPF và DKIM đều pass** mới pass DMARC. Điều kiện nền tảng là **ít nhất một trong hai cơ chế pass và có alignment phù hợp với From**. Tuy nhiên, triển khai cả SPF lẫn DKIM đúng cách thường giúp tăng khả năng xác thực khi có forwarding hoặc các tuyến gửi khác nhau.

### 1.1. Mô hình luồng kiểm tra

```text
Spring application
  |
  | MIME message:
  | From: notices@example.com
  | Subject: ...
  |
  v
Outbound SMTP relay/provider
  |                                DNS
  | MAIL FROM: bounce@bounces.example.com
  | IP: 192.0.2.25                  |
  | DKIM signs with d=example.com   |
  +---------------------------+----+
                              |
                              v
Receiving SMTP server
   |
   +--> SPF: IP được bounces.example.com cho phép?
   |
   +--> DKIM: chữ ký d=example.com xác thực được?
   |
   +--> DMARC: cơ chế nào PASS + aligned với From example.com?
   |
   +--> Áp dụng chính sách, spam filtering và quy tắc riêng
   |
   v
Delivery / spam / quarantine / reject
```

Các IP và miền trong ví dụ là dữ liệu minh họa, không phải thông số của nhà cung cấp thực tế.

## 2. Phân biệt bốn danh tính dễ bị nhầm

Một thông điệp có thể có nhiều địa chỉ và miền. Nếu nhầm chúng, việc cấu hình SPF/DMARC rất dễ sai.

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| **Header From** (`RFC5322.From`) | `notices@example.com` | Địa chỉ người gửi hiển thị cho người nhận; DMARC lấy miền ở đây. |
| **Envelope sender** (`RFC5321.MailFrom`) | `bounce@bounces.example.com` | Địa chỉ dùng trong phiên SMTP `MAIL FROM` và làm đường trả về cho nhiều thông báo lỗi giao thư; SPF thường kiểm tra domain này. |
| **DKIM signing domain** (`d=`) | `example.com` | Miền nhận trách nhiệm ký thông điệp theo DKIM. |
| **SMTP server hostname** | `smtp.provider.example` | Endpoint ứng dụng kết nối để gửi; không nhất thiết là miền trong Header From. |

Ví dụ:

```text
From: Example Store <notices@example.com>
Reply-To: support@example.com

SMTP envelope:
MAIL FROM:<bounce@bounces.example.com>

DKIM-Signature: ... d=example.com; s=mail2026; ...
```

Giải thích:
- Người dùng nhìn thấy `notices@example.com`.
- SMTP dùng `bounce@bounces.example.com` để xử lý một số loại delivery failure.
- DKIM signer xác nhận chữ ký thuộc `example.com`.
- Provider có thể là một hệ thống khác như `smtp.provider.example`.

**SPF không trực tiếp kiểm tra `From: notices@example.com`.** DMARC mới xét việc kết quả SPF có aligned với miền `example.com` của From hay không.

### 2.1. Return-Path có phải From không?

Không. `Return-Path` thường được MTA đích thêm vào thư đã nhận để ghi nhận envelope sender, ví dụ:

```text
Return-Path: <bounce@bounces.example.com>
```

Không nên tự đặt một `Return-Path` header rồi tưởng rằng đã đổi SMTP envelope. Muốn thay envelope sender phải cấu hình cơ chế SMTP thích hợp, như `mail.smtp.from` của Jakarta Mail SMTP transport, hoặc cấu hình custom bounce domain tại provider. Provider có thể tự thay đổi envelope sender để quản lý bounce/tracking.

### 2.2. Reply-To có ảnh hưởng SPF hay DMARC không?

`Reply-To: support@example.com` điều khiển địa chỉ trả lời theo cách mail client dùng. Nó **không phải identifier dùng để SPF xác thực** và không quyết định From domain mà DMARC kiểm tra.

```java
helper.setFrom("notices@example.com");
helper.setReplyTo("support@example.com");
```

Hai dòng này không tự cấu hình envelope sender hoặc DKIM signing domain.

### 2.3. HELO/EHLO khi envelope sender rỗng

Trong một số thông điệp hệ thống, đặc biệt delivery status notification, SMTP sử dụng `MAIL FROM:<>`. SPF có thể sử dụng identifier dựa trên `HELO/EHLO` trong các trường hợp theo quy tắc SPF. Vì vậy, không nên suy ra mọi kết quả SPF đều xuất phát từ địa chỉ Header From hoặc một hộp thư cụ thể.

## 3. SPF: công bố hạ tầng được phép gửi

SPF thường được công bố bằng **DNS TXT record** ở miền dùng trong SMTP envelope.

Ví dụ miền `bounces.example.com` chỉ chấp nhận một số IP và provider được phê duyệt:

```dns
bounces.example.com. IN TXT "v=spf1 ip4:192.0.2.25 include:_spf.provider.example -all"
```

Ý nghĩa:
- `v=spf1`: record SPF.
- `ip4:192.0.2.25`: địa chỉ IP minh họa được cho phép.
- `include:_spf.provider.example`: tham chiếu cơ chế cho phép IP theo SPF policy của provider minh họa.
- `-all`: những nguồn còn lại không được phép theo record.

`_spf.provider.example` chỉ là tên giả cho tài liệu; khi triển khai thực tế phải lấy chính xác host/record do SMTP provider công bố. Không copy nguyên domain minh họa vào DNS thật.

### 3.1. Các mechanism thường gặp

| Mechanism | Ví dụ | Vai trò |
|---|---|---|
| `ip4` | `ip4:192.0.2.25` | Cho phép IP hoặc mạng IPv4. |
| `ip6` | `ip6:2001:db8::/32` | Cho phép IP hoặc mạng IPv6. |
| `include` | `include:_spf.provider.example` | Kết hợp policy SPF của bên cung cấp theo quy tắc include. |
| `a` | `a:mail.example.com` | Đối chiếu IP với DNS A/AAAA của hostname. |
| `mx` | `mx:example.com` | Đối chiếu theo các MX hosts và địa chỉ của chúng. |
| `exists` | `exists:check.example.com` | Cơ chế dựa trên DNS existence, thường dùng trong cấu hình phức tạp. |
| `redirect` | `redirect=_spf.example.com` | Chuyển việc đánh giá chính sách theo điều kiện của SPF. |
| `all` | `-all`, `~all` | Quy định kết quả mặc định cho nguồn chưa khớp trước đó. |

`include` không có nghĩa là chép record TXT của provider vào cùng chuỗi một cách máy móc; nó có quy tắc đánh giá riêng và có thể phát sinh DNS lookup. Chỉ thêm provider thực sự đang gửi với envelope domain của bạn.

### 3.2. Các qualifier của SPF

| Ký hiệu | Kết quả khi mechanism khớp | Ý nghĩa thường dùng |
|---|---|---|
| `+` | Pass | Được cho phép; nếu không ghi qualifier thì mặc định là `+`. |
| `-` | Fail | Không được cho phép theo policy. |
| `~` | Softfail | Miền cho rằng nguồn không được ủy quyền nhưng đưa ra mức khẳng định mềm hơn. |
| `?` | Neutral | Không khẳng định cho phép hay từ chối. |

Ví dụ:

```dns
example.com. IN TXT "v=spf1 include:_spf.provider.example ~all"
```

`~all` không giống `-all`. Khi triển khai, policy SPF nên phản ánh danh sách nguồn gửi thực sự và mức chắc chắn của chủ miền. **SPF fail không đồng nghĩa receiver bắt buộc từ chối email**: kết quả còn tham gia các quy tắc kiểm tra, DMARC, chính sách receiver và reputation.

### 3.3. SPF record đặt ở đâu?

**Đặt SPF tại miền được SPF đánh giá**, thường là domain của `RFC5321.MailFrom`.

Ví dụ:
- Header From: `billing@example.com`.
- MAIL FROM: `bounce@bounces.example.com`.

SPF lookup sẽ cần record tại `bounces.example.com` (theo identifier được đánh giá), **không tự động chuyển sang SPF ở `example.com`**.

Chỉ thêm SPF ở apex `example.com` mà bỏ quên bounce subdomain có thể khiến SPF kiểm tra trên `bounces.example.com` thất bại hoặc không có policy. Nếu provider quản lý riêng custom return-path, hãy theo hướng dẫn của họ về CNAME/TXT/MX cho bounce domain.

### 3.4. Chỉ có một SPF TXT policy cho mỗi owner name

Có thể tồn tại nhiều TXT record cho mục đích khác nhau (verification, DKIM, v.v.), nhưng **không nên có hai record riêng cùng bắt đầu `v=spf1` ở cùng một DNS owner name**.

Sai:

```dns
example.com. IN TXT "v=spf1 include:_spf.provider-a.example -all"
example.com. IN TXT "v=spf1 include:_spf.provider-b.example -all"
```

Điều này có thể gây SPF `permerror` vì nhiều SPF records. Nếu cả hai provider cùng gửi bằng một envelope domain cần đánh giá record đó, phải hợp nhất policy phù hợp:

```dns
example.com. IN TXT "v=spf1 include:_spf.provider-a.example include:_spf.provider-b.example -all"
```

Tuy nhiên, đừng hợp nhất mù quáng: kiểm tra **envelope domain thực tế** của từng provider, số DNS lookup và nguồn IP được cho phép. Có trường hợp mỗi provider dùng bounce subdomain riêng nên không cần cùng nằm trong một SPF record.

### 3.5. Giới hạn DNS lookup trong SPF

SPF có giới hạn số lần dùng các cơ chế/modifier cần DNS lookup trong quá trình đánh giá, thông thường **tối đa 10** cho các mục như `include`, `a`, `mx`, `ptr`, `exists` và `redirect` theo quy tắc SPF. Các include có thể lồng nhau và tiêu tốn lookup ở những tầng khác.

Ví dụ một record nhiều provider:

```dns
example.com. IN TXT "v=spf1 include:_spf.a.example include:_spf.b.example include:_spf.c.example -all"
```

Dù chỉ nhìn thấy ba `include`, mỗi provider có thể tiếp tục include nhiều miền. Vượt giới hạn có thể dẫn đến `permerror` và làm mất lợi ích SPF.

Các lưu ý:
- `ip4`/`ip6` không tạo DNS lookup như `include`.
- Đếm lookup theo quá trình evaluation, không chỉ đếm từ khóa ở một record.
- Tránh dùng `ptr` khi không thực sự cần và hiểu giới hạn của nó.
- Giảm các nguồn gửi không còn dùng.
- Không “flatten” SPF thành danh sách IP cố định nếu không quản lý được việc provider đổi IP; cách đó có thể nhanh chóng lỗi thời.

### 3.6. SPF không xác nhận nội dung email

SPF kiểm tra sự ủy quyền của IP/SMTP identity. Nó **không ký subject, nội dung HTML, attachment hay header From**. Vì vậy, cần DKIM và DMARC để xác thực ở các lớp bổ sung.

## 4. DKIM: ký thông điệp bằng danh tính miền

DKIM sử dụng chữ ký số. Một hệ thống ở phía gửi giữ **private key** để ký các header đã chọn và phần thân thông điệp theo thuật toán/canonicalization đã cấu hình. Hệ thống nhận đọc **public key** được công bố trong DNS của miền ký để kiểm tra.

Một header minh họa:

```text
DKIM-Signature: v=1; a=rsa-sha256; c=relaxed/relaxed;
 d=example.com; s=mail2026;
 h=from:to:subject:date:mime-version;
 bh=BODY_HASH_PLACEHOLDER;
 b=SIGNATURE_PLACEHOLDER
```

Các trường quan trọng:

| Tham số | Ý nghĩa |
|---|---|
| `v=1` | DKIM signature version. |
| `a=rsa-sha256` | Thuật toán chữ ký minh họa. |
| `d=example.com` | **Signing domain** — miền chịu trách nhiệm chữ ký. |
| `s=mail2026` | **Selector** — tên dùng để tìm public key DNS. |
| `h=...` | Danh sách header fields được ký; `From` phải được ký theo DKIM. |
| `bh=...` | Hash của phần thân sau canonicalization. |
| `b=...` | Chữ ký mật mã. |
| `c=relaxed/relaxed` | Cách chuẩn hóa header/body trước khi ký và xác minh. |

`bh` và `b` trong ví dụ là placeholder, không phải chữ ký hợp lệ. DKIM không mã hóa nội dung để người khác không đọc được; nó tạo bằng chứng rằng dữ liệu được ký chưa bị sửa ngoài phạm vi mà canonicalization cho phép và chữ ký tương ứng với miền `d=`.

### 4.1. DKIM public key nằm ở DNS selector

Với:
- `d=example.com`;
- `s=mail2026`;

receiver tra cứu:

```text
mail2026._domainkey.example.com
```

TXT record minh họa:

```dns
mail2026._domainkey.example.com. IN TXT "v=DKIM1; k=rsa; p=BASE64_PUBLIC_KEY_PLACEHOLDER"
```

`p=` là phần public key được biểu diễn theo định dạng của DKIM record; nó **không phải private key**, không có PEM header hoặc khoảng trắng tùy ý. Chuỗi trên là placeholder, không dùng để xác minh thật.

DNS provider có thể chia một TXT value dài thành nhiều quoted strings vì giới hạn mỗi chuỗi; resolver sẽ nối các chuỗi của cùng TXT record theo quy tắc DNS. Cần tránh vô tình tạo nhiều TXT policy mâu thuẫn ở cùng selector.

### 4.2. Ai thực sự ký DKIM?

Trong kiến trúc Spring Mail phổ biến:

```text
Spring Boot / JavaMailSender
         |
         | raw MIME via SMTP
         v
Authorized outbound SMTP provider / MTA
         |
         | DKIM signing with domain key
         v
Receiving MX
         |
         | look up selector._domainkey.domain
         v
DKIM validation
```

`MimeMessageHelper` giúp tạo text/HTML, attachment, CID và header, nhưng **không tự cấu hình DNS và không mặc định ký DKIM chỉ vì dùng JavaMailSender**.

Thông thường DKIM signing được thiết lập tại SMTP provider hoặc outbound MTA:
1. Xác minh bạn sở hữu domain.
2. Provider cấp selector/DNS records hoặc hướng dẫn tạo key.
3. Công bố public key/record đúng DNS zone.
4. Provider lưu hoặc quản lý private key theo cơ chế của họ.
5. Bật ký thư bằng đúng signing domain.
6. Kiểm tra một email nhận thực tế có `dkim=pass` và `header.d` mong muốn.

Nếu tổ chức tự vận hành mail server, việc ký có thể thực hiện bằng DKIM signer ở outbound MTA. Không nên tự lưu private key DKIM trong source code hoặc đính kèm nó vào email.

### 4.3. DKIM selector cho phép quay vòng khóa

Một domain có thể dùng nhiều selectors:

```text
mail2026._domainkey.example.com
mail2027._domainkey.example.com
marketing1._domainkey.example.com
transactional1._domainkey.example.com
```

Mỗi selector ánh xạ tới public key. Điều này cho phép:
- tách khóa giữa các hệ thống;
- triển khai khóa mới trước khi đổi signer;
- rollback theo kế hoạch;
- duy trì public key cũ trong một thời gian phù hợp để các thư đã ký còn được xác minh;
- thu hồi key bị lộ theo quy trình.

**Không xóa selector cũ quá sớm** nếu thư đã gửi còn có thể được receiver xác minh lại hoặc hệ thống xử lý chậm. Thời gian giữ và thời điểm thu hồi cần theo chính sách bảo mật của tổ chức.

### 4.4. DKIM không đồng nghĩa với nội dung chắc chắn đúng hoặc an toàn

`dkim=pass` không có nghĩa thông điệp không phải spam, không chứa malware và không giả mạo nhãn hiệu nếu signing domain không phải miền hiển thị trong From. Một hệ thống gửi thư rác có thể ký DKIM hợp lệ bằng chính domain của nó.

Đó là lý do DMARC cần kiểm tra **alignment giữa signing domain và From domain**.

### 4.5. Điều gì làm DKIM fail?

Một số nguyên nhân:
- Public key DNS sai hoặc selector chưa được công bố.
- Sender ký bằng key không khớp public key.
- Provider ký với `d=` sai domain.
- Một hệ thống downstream thay body hoặc headers đã ký sau khi chữ ký được tạo.
- Mail gateway thêm footer, sửa link hoặc thay MIME.
- DNS propagation hoặc record bị vô hiệu hóa.
- Thuật toán/key không được receiver hỗ trợ theo policy.

Canonicalization `relaxed` chịu được một số thay đổi whitespace/form nhất định, nhưng **không cho phép sửa nội dung tùy ý**. Nếu một MTA sửa body sau khi đã ký, chữ ký có thể thất bại.

Đặt DKIM signer **sau các bước biến đổi nội dung được kiểm soát** khi có thể, hoặc đảm bảo downstream không làm hỏng chữ ký.

## 5. DMARC: xác thực gắn với miền người nhận nhìn thấy

DMARC lấy domain trong header `RFC5322.From` làm trung tâm. Nó sử dụng kết quả SPF và DKIM, nhưng không đơn giản là “SPF pass hoặc DKIM pass” trong mọi trường hợp: kết quả pass còn phải **aligned** với From domain.

DMARC đưa ra:
- một cơ chế xác định email có pass theo miền From không;
- chính sách mong muốn khi không pass;
- cơ chế nhận báo cáo tổng hợp và, nếu receiver hỗ trợ, một số loại failure report.

### 5.1. Công bố DMARC TXT record

Với Header From domain `example.com`, bắt đầu bằng:

```dns
_dmarc.example.com. IN TXT "v=DMARC1; p=none; rua=mailto:dmarc-reports@example.com; adkim=r; aspf=r"
```

Ý nghĩa:

| Tag | Vai trò |
|---|---|
| `v=DMARC1` | Phiên bản record DMARC. |
| `p=none` | Công bố chính sách giám sát; không yêu cầu receiver áp dụng cách ly/từ chối chỉ vì DMARC fail. |
| `rua=mailto:...` | Địa chỉ nhận aggregate reports nếu receiver có gửi. |
| `adkim=r` | DKIM relaxed alignment. |
| `aspf=r` | SPF relaxed alignment. |

Giá trị `adkim=r` và `aspf=r` thường là mặc định khi không khai báo; viết rõ giúp người vận hành đọc cấu hình. DMARC policy được **receiving system** cân nhắc, không phải một lệnh bảo đảm mọi receiver xử lý hoàn toàn giống nhau.

### 5.2. Ba mức chính sách

| Tag | Ý định của miền gửi đối với email DMARC fail | Cách dùng |
|---|---|---|
| `p=none` | Theo dõi, báo cáo; không yêu cầu hành động xử lý theo DMARC policy | Giai đoạn quan sát các nguồn gửi. |
| `p=quarantine` | Yêu cầu receiver xử lý thận trọng, thường vào spam/quarantine | Bước tăng cường sau khi đã kiểm soát nguồn gửi. |
| `p=reject` | Yêu cầu receiver từ chối email không đạt DMARC | Mức bảo vệ mạnh hơn trước From-domain spoofing. |

`p=none` **không đảm bảo email vào Inbox**; receiver vẫn có bộ lọc chống spam, malware và các policy riêng. `p=reject` cũng không phải mệnh lệnh được mọi receiver thực thi y hệt; quyết định cuối cùng phụ thuộc hệ thống nhận, ngoại lệ và chính sách địa phương.

### 5.3. DMARC không tự ký email

Thêm:

```dns
_dmarc.example.com. IN TXT "v=DMARC1; p=reject"
```

không tự làm SPF hay DKIM pass. Nó chỉ công bố chính sách và yêu cầu xác thực/alignment. Nếu hệ thống sending chưa có SPF/DKIM aligned, chuyển thẳng sang `p=reject` có thể làm **email hợp lệ của chính doanh nghiệp** bị từ chối.

Vì vậy, quy trình rollout phải bắt đầu bằng **kiểm kê tất cả các nguồn gửi**, không phải chỉ thay một TXT record.

## 6. DMARC alignment: yếu tố quyết định

Giả sử người nhận thấy:

```text
From: Example Store <notices@example.com>
```

Miền From là `example.com`. DMARC sẽ kiểm tra:

- **SPF alignment:** domain dùng cho SPF, thông thường domain của `MAIL FROM`, có aligned với `example.com` không? Và bản thân SPF có `pass` không?
- **DKIM alignment:** có ít nhất một chữ ký DKIM được xác minh `pass` với `d=` aligned `example.com` không?

Chỉ cần một nhánh thành công:

```text
DMARC PASS
  =
    [SPF PASS AND SPF domain aligned with Header From]
  OR
    [DKIM PASS AND DKIM d= aligned with Header From]
```

Nếu cả hai nhánh đều không đạt, DMARC fail.

### 6.1. Relaxed alignment

Trong relaxed alignment (`aspf=r`, `adkim=r`), hai miền có thể được xem là aligned nếu cùng **Organizational Domain** theo quy tắc DMARC phù hợp.

Ví dụ thường gặp:
- From domain: `example.com`.
- MAIL FROM domain: `bounces.example.com`.
- DKIM d=: `mail.example.com`.

Với Organizational Domain là `example.com`, hai subdomains có thể aligned theo relaxed mode.

Không xác định Organizational Domain bằng cách chỉ lấy “hai nhãn cuối” của DNS name. Các public suffix như `co.uk` khiến cách đó sai. Hệ thống kiểm tra DMARC phải dựa vào quy tắc/public suffix data phù hợp với triển khai.

### 6.2. Strict alignment

Trong strict alignment (`aspf=s` hoặc `adkim=s`), tên miền dùng so sánh phải khớp chính xác theo quy tắc tương ứng.

Ví dụ:

```text
Header From domain: example.com

MAIL FROM domain: bounces.example.com
  -> SPF strict alignment: KHÔNG khớp.

DKIM d=example.com
  -> DKIM strict alignment: KHỚP.

DKIM d=marketing.example.com
  -> DKIM strict alignment: KHÔNG khớp.
```

Ngay cả khi SPF trả `pass` cho `bounces.example.com`, nó vẫn **không giúp DMARC pass qua nhánh SPF strict** nếu From domain là `example.com`. Nếu DKIM `d=example.com` pass, DMARC vẫn có thể pass qua DKIM.

### 6.3. Bảng quyết định minh họa

Giả sử Header From luôn là `notices@example.com` và DMARC dùng relaxed alignment:

| SPF | MAIL FROM domain | DKIM | DKIM d= | DMARC |
|---|---|---|---|---|
| Pass | `bounces.example.com` | Fail | — | **Pass** nhờ SPF aligned. |
| Fail | `bounces.example.com` | Pass | `example.com` | **Pass** nhờ DKIM aligned. |
| Pass | `provider.other.example` | Pass | `provider.other.example` | **Fail** vì cả hai domain không aligned. |
| Pass | `provider.other.example` | Pass | `example.com` | **Pass** nhờ DKIM aligned. |
| Pass | `bounces.example.com` | Pass | `provider.other.example` | **Pass** nhờ SPF aligned. |
| Fail | `bounces.example.com` | Fail | — | **Fail**. |
| Neutral | `bounces.example.com` | Pass | `example.com` | **Pass** nhờ DKIM aligned. |

Bảng này minh họa logic alignment; mọi kết quả pass/fail được giả định là kết quả xác thực thực tế đã được receiver tính toán.

### 6.4. Ví dụ SPF pass nhưng DMARC fail

```text
From: notices@example.com
MAIL FROM: bounce@provider-other.example
Authentication-Results:
  spf=pass smtp.mailfrom=provider-other.example;
  dkim=pass header.d=provider-other.example;
  dmarc=fail header.from=example.com
```

SPF và DKIM đều **pass** cho domain của provider, nhưng không có domain nào aligned với `example.com`. Đây là trường hợp điển hình khi dùng SMTP service chưa cấu hình domain authentication cho khách hàng.

Giải pháp có thể là:
- Cấu hình custom MAIL FROM/bounce domain thuộc `example.com` cho SPF alignment; hoặc
- Cấu hình DKIM signing domain `d=example.com`; hoặc
- Thực hiện cả hai theo hướng dẫn provider.

Chỉ thêm SPF record ở `example.com` mà provider vẫn gửi envelope bằng `provider-other.example` **không tự biến SPF thành aligned**.

## 7. Domain/subdomain policy trong DMARC

### 7.1. Tổ chức có nhiều subdomains

Ví dụ:
- `example.com` cho email công ty.
- `billing.example.com` cho hóa đơn.
- `news.example.com` cho marketing.
- `alerts.example.com` cho cảnh báo.

Có thể thiết kế cách ly chức năng qua subdomain, riêng sender và DKIM selector. DMARC policy có thể được công bố ở từng subdomain hoặc được áp dụng theo cơ chế policy của Organizational Domain khi phù hợp.

### 7.2. Tag sp cho subdomains

Ví dụ:

```dns
_dmarc.example.com. IN TXT "v=DMARC1; p=reject; sp=quarantine; rua=mailto:dmarc-reports@example.com"
```

`p=reject` là chính sách tại domain theo quy tắc khám phá áp dụng, còn `sp=quarantine` công bố chính sách dành cho các subdomain theo quy tắc DMARC. Một subdomain có record DMARC riêng có thể có chính sách cụ thể của nó.

Không nên suy luận rằng một record ở apex luôn áp dụng chính xác như vậy cho mọi domain lồng nhiều cấp trong mọi tình huống; DMARC discovery/policy có quy tắc rõ ràng và phụ thuộc Organizational Domain. Khi triển khai, cần kiểm tra thực tế với từng From domain sử dụng.

### 7.3. Chọn domain cho từng hệ thống gửi

Một cách phân tách:

| Hệ thống | Header From | MAIL FROM | DKIM d= |
|---|---|---|---|
| Giao dịch | `billing@example.com` | `bounce@bounces.example.com` | `example.com` |
| Marketing | `news@news.example.com` | `bounce@bounces.news.example.com` | `news.example.com` |
| Alerts | `alerts@alerts.example.com` | `bounce@bounces.alerts.example.com` | `alerts.example.com` |

Ví dụ được thiết kế để SPF/DKIM có thể aligned theo relaxed policy tương ứng. Nếu tổ chức yêu cầu strict alignment, cần điều chỉnh domain chính xác và xác minh lại.

Chia subdomain giúp vận hành policy, log, reputation và quyền truy cập nhưng **không tự tạo SPF, DKIM hoặc DMARC pass**; từng tuyến gửi vẫn phải được cấu hình đúng.

## 8. SPF và DKIM trong Spring Framework Mail: trách nhiệm ở đâu?

Ứng dụng Spring Mail có thể quyết định:
- Header From/Reply-To;
- MIME text/HTML và attachment;
- SMTP host/port/authentication;
- SMTP envelope sender trong phạm vi Jakarta Mail/provider cho phép;
- các custom headers/correlation IDs.

Nhưng **ứng dụng không tự công bố DNS TXT records**, không tự cấp chứng chỉ DKIM và không tự làm receiver tin domain.

Một kiến trúc điển hình:

```text
Spring Boot
  |
  | JavaMailSender builds message
  | From: notices@example.com
  v
SMTP provider / outbound MTA
  |
  +--> Applies envelope sender
  |     bounce@bounces.example.com
  |
  +--> Signs DKIM with
  |     d=example.com; s=mail2026
  |
  v
Receiving MTA
  |
  +--> SPF: DNS TXT at bounces.example.com
  +--> DKIM: DNS TXT at mail2026._domainkey.example.com
  +--> DMARC: DNS TXT at _dmarc.example.com
  |
  v
Authentication results + local filtering
```

Để gửi bằng domain riêng, thường cần hoàn thành bước **domain verification/authentication trong bảng quản trị SMTP provider** trước khi đưa ứng dụng vào production.

## 9. Ví dụ cấu hình Spring Boot kết hợp domain authentication

Giả sử doanh nghiệp sở hữu `example.com`, đã xác minh domain với SMTP provider và cấu hình cho provider ký DKIM bằng `d=example.com`.

```yaml
spring:
  mail:
    host: smtp.provider.example
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
          from: bounce@bounces.example.com
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

Lưu ý:
- `smtp.provider.example` là endpoint minh họa, dùng host thật do provider cấp.
- `from: bounce@bounces.example.com` nằm dưới `spring.mail.properties.mail.smtp.from`: đó là thuộc tính SMTP envelope sender của Jakarta Mail transport trong cấu hình đơn giản này.
- Provider có thể **ghi đè hoặc không cho phép** custom envelope sender. Phải kiểm tra thông điệp thực tế và cấu hình custom return-path/bounce domain của provider.
- TLS/hostname verification bảo vệ chặng gửi từ ứng dụng tới SMTP server, **khác** với SPF/DKIM/DMARC.
- Password được lấy từ secret store/biến môi trường; không commit credential thật.
- Nếu có nhiều sender/tenant khác envelope domain, một property toàn cục có thể không phù hợp; cần thiết kế sender profiles hoặc cơ chế per-message đã được provider hỗ trợ.

### 9.1. JavaMailSender tạo From và Reply-To

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderConfirmationMailer {

    private final JavaMailSender mailSender;

    public OrderConfirmationMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(
            String recipient,
            String orderId,
            String orderUrl) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        // Header From: miền trung tâm của DMARC.
        helper.setFrom("notices@example.com");
        helper.setReplyTo("support@example.com");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đơn hàng " + orderId);

        String plain = """
            Đơn hàng %s đã được xác nhận.
            Xem chi tiết: %s
            """.formatted(orderId, orderUrl);

        String html = """
            <html><body>
              <p>Đơn hàng của bạn đã được xác nhận.</p>
              <p><a href="%s">Xem chi tiết đơn hàng</a></p>
            </body></html>
            """.formatted(orderUrl);

        // Với dữ liệu không tin cậy, cần escaping HTML theo ngữ cảnh,
        // và URL phải được kiểm tra bằng policy của ứng dụng.
        helper.setText(plain, html);

        mailSender.send(message);
    }
}
```

Đây là ví dụ tập trung vào quan hệ From/domain. Trong production, dùng template engine có escaping đúng cho HTML; không nối dữ liệu tùy ý từ người dùng vào attribute URL.

Trong ví dụ:
- Spring Mail đặt Header From là `notices@example.com`.
- Jakarta Mail/SMTP provider dùng envelope sender theo cấu hình và policy thực tế.
- Provider/MTA ký DKIM nếu đã được thiết lập cho domain.
- Receiver kiểm tra SPF/DKIM/DMARC theo DNS records của các domain liên quan.

**Không có lệnh `helper.enableSpf()`, `helper.enableDkim()` hoặc `helper.enableDmarc()` trong `MimeMessageHelper`.** Những cơ chế này không được bật chỉ bằng một method của Spring helper.

### 9.2. Header Return-Path không phải công tắc SPF

Sai về mặt thiết kế:

```java
message.setHeader("Return-Path", "<bounce@bounces.example.com>");
```

Việc tự ghi header này không bảo đảm SMTP session dùng đúng `MAIL FROM`. Địa chỉ Return-Path thường do hệ thống nhận tạo từ envelope sender. Muốn SPF kiểm tra đúng domain, phải điều khiển envelope sender tại **SMTP transport/provider** và công bố SPF ở domain được dùng thật.

### 9.3. SMTP AUTH không đồng nghĩa SPF/DKIM/DMARC pass

Username/password chỉ chứng minh tài khoản của ứng dụng được SMTP provider chấp nhận. Nó **không tự xác thực quyền sử dụng Header From domain** ở phía receiver.

Một tài khoản SMTP có thể đăng nhập thành công nhưng:
- provider từ chối địa chỉ From chưa verified;
- provider ký DKIM bằng domain riêng của họ;
- MAIL FROM thuộc domain của provider;
- SPF pass nhưng DMARC fail vì thiếu alignment.

Cần kiểm tra domain authentication riêng.

## 10. Ví dụ bộ DNS records cho một miền gửi

Giả sử:
- Header From là `notices@example.com`.
- SMTP provider dùng bounce domain `bounces.example.com`.
- Provider DKIM signing bằng `d=example.com` và selector `mail2026`.
- Doanh nghiệp bắt đầu giám sát DMARC.

Bộ record minh họa:

```dns
; SPF tại đúng MAIL FROM domain:
bounces.example.com. IN TXT "v=spf1 include:_spf.provider.example -all"

; DKIM public key:
mail2026._domainkey.example.com. IN TXT "v=DKIM1; k=rsa; p=PUBLIC_KEY_BASE64_PLACEHOLDER"

; DMARC policy cho Header From domain:
_dmarc.example.com. IN TXT "v=DMARC1; p=none; rua=mailto:dmarc-reports@example.com; adkim=r; aspf=r"
```

Các placeholder **không dùng trực tiếp** trong DNS production. Provider có thể yêu cầu CNAME cho DKIM thay vì TXT public key do bạn tự đặt. Khi đó phải làm theo record chính xác do provider cấp và xác nhận resolution tới public key hợp lệ.

### 10.1. DNS propagation và TTL

Khi thay record:
- cần tính đến TTL và cache của recursive resolvers;
- gửi thử ngay sau khi lưu DNS chưa chắc phản ánh cấu hình mới;
- mỗi resolver có thể thấy thay đổi ở thời điểm khác nhau;
- đổi chính sách từ `p=none` sang `p=reject` cần chờ đủ thời gian và kiểm tra dữ liệu.

Không thay đổi nhiều SPF/DKIM/DMARC record cùng lúc rồi kết luận lỗi từ một lần gửi thử. Ghi lại phiên bản record, timestamp và nguồn gửi.

### 10.2. DKIM có thể dùng CNAME

Một số nhà cung cấp yêu cầu:

```dns
mail2026._domainkey.example.com. IN CNAME mail2026.example-com._domainkey.provider.example.
```

Đây là mẫu giả định minh họa cú pháp, không phải host thật. Provider quản lý public key ở DNS zone của họ; khi receiver tra cứu, DNS có thể dẫn tới TXT DKIM key.

Không tự chọn CNAME target. Chỉ dùng record mà provider cung cấp và không tạo một TXT lẫn CNAME mâu thuẫn tại cùng owner name.

## 11. Quy trình triển khai DMARC theo giai đoạn

Đặt `p=reject` ngay khi chưa biết ai đang gửi thư thay mặt domain có thể làm hỏng các luồng hợp lệ như:
- email xác nhận từ ứng dụng Spring Boot;
- CRM/marketing automation;
- bộ phận hỗ trợ khách hàng;
- hệ thống hóa đơn;
- helpdesk/ticketing;
- công cụ khảo sát;
- hệ thống nhân sự;
- dịch vụ thông báo qua bên thứ ba.

Một lộ trình hợp lý:

### Giai đoạn 1 — Kiểm kê nguồn gửi

Liệt kê:
- tất cả SMTP providers và outbound MTA;
- các From domains/subdomains;
- envelope MAIL FROM/return-path domain;
- DKIM d=/selectors;
- IP hoặc SPF include provider;
- địa chỉ nhận báo cáo DMARC;
- owner chịu trách nhiệm từng nguồn.

Tách rõ email giao dịch, marketing và nội bộ nếu chúng có nhà cung cấp/chính sách khác nhau.

### Giai đoạn 2 — Cấu hình SPF và DKIM

Với từng nguồn:
1. Xác minh domain tại provider.
2. Thiết lập SPF cho envelope domain thực sự.
3. Thiết lập DKIM signing domain aligned.
4. Xác nhận public key/selector trong DNS.
5. Gửi test email.
6. Đọc `Authentication-Results` từ hệ thống nhận đáng tin cậy.
7. Đối chiếu SPF/DKIM identity với Header From.

Ưu tiên **ít nhất một đường xác thực aligned đáng tin cậy**, tốt nhất có cả SPF và DKIM aligned trong kiến trúc cho phép.

### Giai đoạn 3 — Bật DMARC p=none và thu thập báo cáo

```dns
_dmarc.example.com. IN TXT "v=DMARC1; p=none; rua=mailto:dmarc-reports@example.com"
```

Quan sát:
- lượng email từ các IP/provider;
- tỷ lệ SPF pass/fail;
- tỷ lệ DKIM pass/fail;
- tỷ lệ DMARC pass/fail;
- nguồn gửi hợp lệ chưa được cấu hình;
- nguồn giả mạo và các record sai.

Báo cáo DMARC aggregate có thể đến trễ và không phải mọi receiver đều gửi. Đừng chỉ dựa trên một mẫu email rồi đánh giá toàn bộ domain đã sẵn sàng.

### Giai đoạn 4 — Khắc phục nguồn hợp lệ bị fail

Ví dụ:
- CRM ký DKIM bằng domain của vendor: bật custom DKIM domain nếu hỗ trợ.
- Transactional sender dùng bounce domain ngoài tổ chức: thiết lập custom return-path hoặc DKIM aligned.
- Một node outbound chưa có SPF IP: cập nhật nguồn được phê duyệt.
- DKIM key không resolve: sửa selector record.
- Mailing list làm sửa body: cân nhắc cách xử lý theo chính sách list/From và đặc điểm forwarding.

Không dùng `p=none` vĩnh viễn chỉ vì có lỗi chưa xử lý. Nhưng cũng không nâng cấp enforcement khi còn nhiều nguồn hợp lệ chưa xác thực.

### Giai đoạn 5 — Chuyển dần quarantine và reject

Khi các nguồn hợp lệ đã có alignment:
- cân nhắc `p=quarantine` cho miền/nhóm phù hợp;
- giám sát false positive, bounce và inbox placement;
- xử lý ngoại lệ có lý do;
- nâng sang `p=reject` khi sẵn sàng;
- nếu cần, dùng `sp` để điều khiển chính sách subdomains theo quy tắc DMARC.

Có thể triển khai theo miền/subdomain hoặc theo từng giai đoạn, tùy rủi ro và khả năng vận hành. Các tag như `pct` từng được dùng để triển khai chính sách theo tỷ lệ trong các triển khai DMARC, nhưng mức hỗ trợ và ý nghĩa có thể khác theo tiêu chuẩn/receiver; không nên dựa vào đó như một công cụ bảo đảm rollout nếu chưa xác nhận hệ thống thực tế.

## 12. DMARC reporting: rua, ruf và quyền riêng tư

### 12.1. Aggregate reports với rua

Ví dụ:

```dns
_dmarc.example.com. IN TXT "v=DMARC1; p=none; rua=mailto:dmarc-reports@example.com"
```

`rua` chỉ nơi nhận aggregate reports, thường chứa thống kê theo:
- source IP;
- số message;
- SPF result;
- DKIM result;
- DMARC disposition;
- Header From / policy domain;
- các danh tính liên quan và reporting organization.

Report thường ở dạng XML, có thể được nén. Một hộp thư nhận report số lượng lớn nên được tích hợp parser/dashboard và retention phù hợp, không phải mở thủ công từng file.

### 12.2. Báo cáo thất bại ruf

Một số cấu hình DMARC có thể nêu `ruf=mailto:...` để yêu cầu failure/forensic reports, nhưng **không nên giả định receiver sẽ gửi loại báo cáo này**. Nhiều receiver hạn chế hoặc không phát hành vì lo ngại quyền riêng tư. Failure reports có thể chứa metadata nhạy cảm hoặc một phần nội dung.

Nếu dùng, cần kiểm tra chính sách bảo mật, quyền truy cập, retention và khả năng nhận báo cáo thực tế.

### 12.3. Địa chỉ báo cáo nằm ở domain ngoài

Nếu `rua` gửi report đến một domain **khác organizational domain** với domain công bố DMARC, có cơ chế xác nhận external reporting destination theo quy tắc DMARC. Không chỉ thay `rua` sang một địa chỉ ngoài rồi mặc định nhận được báo cáo.

Ví dụ ý tưởng:

```text
DMARC policy domain: example.com
Aggregate report address: dmarc@reports.external.example
```

Domain nhận báo cáo bên ngoài có thể phải công bố record xác thực ủy quyền tương ứng, theo mẫu DMARC external-reporting mà dịch vụ phân tích báo cáo cung cấp. Hãy dùng chính xác hướng dẫn DNS của dịch vụ đó; nếu thiếu authorization, receiver có thể không gửi report.

### 12.4. Báo cáo không phải audit log đầy đủ

DMARC reports không bao phủ mọi email và không thay thế log SMTP/outbox. Chúng giúp hiểu bức tranh xác thực theo miền; để truy nguyên một message cụ thể vẫn cần message key, provider message ID, SMTP logs và delivery events.

## 13. Cách xác minh DNS record

Các lệnh dưới đây là **ví dụ để người học thực hành trong môi trường được phép**, không phải kết quả kiểm tra DNS đã chạy.

### 13.1. Trên Linux/macOS với dig

```bash
# SPF của envelope domain:
dig TXT bounces.example.com

# DKIM của selector mail2026:
dig TXT mail2026._domainkey.example.com

# DMARC của miền From:
dig TXT _dmarc.example.com
```

Có thể dùng `+short` cho output gọn:

```bash
dig +short TXT bounces.example.com
dig +short TXT mail2026._domainkey.example.com
dig +short TXT _dmarc.example.com
```

Đừng chỉ nhìn một DNS record tồn tại là kết luận cơ chế đã pass. SPF còn phụ thuộc IP gửi thật; DKIM còn phụ thuộc chữ ký MIME thật; DMARC còn phụ thuộc From và alignment.

### 13.2. Trên Windows với nslookup/PowerShell

```powershell
nslookup -type=TXT bounces.example.com
nslookup -type=TXT mail2026._domainkey.example.com
nslookup -type=TXT _dmarc.example.com
```

Hoặc PowerShell:

```powershell
Resolve-DnsName bounces.example.com -Type TXT
Resolve-DnsName mail2026._domainkey.example.com -Type TXT
Resolve-DnsName _dmarc.example.com -Type TXT
```

### 13.3. Kiểm tra theo DNS owner name chính xác

Các câu hỏi cần đặt:
1. Header From dùng domain nào?
2. Envelope MAIL FROM thật của provider dùng domain nào?
3. DKIM signature mang `d=` và `s=` nào?
4. SPF nằm ở đúng envelope domain chưa?
5. DKIM TXT/CNAME tại `selector._domainkey.d-domain` có resolve đúng không?
6. DMARC TXT ở đúng `_dmarc.from-domain` hoặc domain áp dụng theo discovery chưa?
7. Có SPF/DMARC records trùng, DNS lookup quá mức hoặc public key bị cắt không?

Nhìn TXT ở `example.com` chưa đủ nếu email dùng `bounces.example.com` hoặc `news.example.com`.

## 14. Xác minh kết quả trong email nhận thật

Sau khi gửi một thư thử tới mailbox/recipient test được phép, xem **raw message source** và phần `Authentication-Results` được thêm bởi hệ thống nhận đáng tin cậy.

Ví dụ minh họa:

```text
From: Example Store <notices@example.com>
Return-Path: <bounce@bounces.example.com>
DKIM-Signature: v=1; a=rsa-sha256; d=example.com; s=mail2026; ...

Authentication-Results: mx.recipient.example;
    spf=pass smtp.mailfrom=bounces.example.com;
    dkim=pass header.d=example.com header.s=mail2026;
    dmarc=pass header.from=example.com
```

Diễn giải:
- SPF pass với envelope domain `bounces.example.com`.
- DKIM pass với signing domain `example.com`.
- From domain là `example.com`.
- Có aligned authentication nên DMARC pass.

**Lưu ý an toàn:** Một người gửi có thể cố chèn `Authentication-Results` giả vào MIME. Khi đọc, phải biết header nào do receiving infrastructure đáng tin cậy tạo, không tin mọi dòng có tên `Authentication-Results` một cách mù quáng.

### 14.1. Authentication-Results có thể cho biết alignment fail

```text
Authentication-Results: mx.recipient.example;
    spf=pass smtp.mailfrom=provider-other.example;
    dkim=pass header.d=provider-other.example;
    dmarc=fail header.from=example.com
```

Vấn đề không phải SPF/DKIM đều fail. Vấn đề là **không có kết quả pass aligned với From**. Cần xem xét custom DKIM signing domain hoặc custom MAIL FROM tại provider.

### 14.2. Header phải kiểm tra sau khi đi qua provider

Đừng chỉ xem `MimeMessage` trong ứng dụng trước `send`:
- DKIM signer thường nằm ở provider và ký **sau** khi Spring đã tạo MIME.
- Envelope sender có thể bị provider thay đổi.
- Receiving MTA là nơi tính SPF/DKIM/DMARC theo IP và DNS ở thời điểm nhận.

Kiểm tra raw mail của mailbox nhận mới cho cái nhìn gần với thực tế deliverability hơn unit test chỉ xác minh `mailSender.send(...)` được gọi.

## 15. Gửi từ nhiều nhà cung cấp bằng một miền

Giả sử doanh nghiệp có:
- Spring Boot gửi email giao dịch qua Provider A.
- Marketing platform gửi chiến dịch qua Provider B.
- Helpdesk gửi thông báo qua Provider C.

Các cách triển khai:

### 15.1. SPF theo đúng MAIL FROM của từng provider

Nếu mỗi provider dùng custom bounce domain khác nhau:

```text
Provider A -> bounce.tx.example.com
Provider B -> bounce.news.example.com
Provider C -> bounce.support.example.com
```

Mỗi bounce domain cần được cấu hình SPF/provider routing theo cơ chế được hỗ trợ. Không nhất thiết gộp mọi IP vào SPF ở apex `example.com`, vì receiver có thể không đánh giá apex khi envelope dùng các subdomains trên.

### 15.2. DKIM selector cho từng provider

```text
tx1._domainkey.example.com       -> Provider A
news1._domainkey.example.com     -> Provider B
support1._domainkey.example.com  -> Provider C
```

Mỗi provider có selector và key material riêng, trong khi signing domain `d=example.com` có thể dùng chung nếu provider hỗ trợ và doanh nghiệp đã xác minh quyền sở hữu miền.

Một provider có thể yêu cầu ký bằng subdomain hoặc cấu trúc CNAME cụ thể. Phải xác nhận alignment cho From domain thực tế.

### 15.3. Tách From subdomain để giảm xung đột vận hành

Có thể dùng:
- `billing@example.com` cho giao dịch;
- `news@news.example.com` cho marketing;
- `help@support.example.com` cho hỗ trợ.

Mỗi luồng có thể có chính sách DMARC, DKIM selector, bounce domain, suppression/feedback handling và monitoring tương ứng. Thiết kế này giúp xử lý lỗi và reputation theo từng chức năng, nhưng không làm email “được giao” tự động.

### 15.4. Không cho provider cũ tồn tại mãi trong SPF

Khi ngừng dùng một provider:
- xác nhận không còn luồng gửi phụ thuộc;
- kiểm tra outbox/queue không còn pending;
- loại include/IP không cần thiết khỏi SPF đúng domain;
- thu hồi signing key/selector theo kế hoạch;
- rà soát quyền domain verification trong provider account.

Để record cũ mãi có thể làm tăng bề mặt lạm dụng và khiến SPF lookup phức tạp.

## 16. Forwarding, mailing list và những giới hạn của SPF/DKIM

### 16.1. Forwarding làm SPF fail

Giả sử mail được gửi:

```text
Provider A -> mailbox1@example.net -> forwarding service -> mailbox2@example.org
```

Khi nhận ở mailbox2, connecting IP có thể là IP của forwarding service chứ không phải IP được envelope domain ban đầu cho phép. Nếu forwarder giữ envelope sender cũ, SPF tại đích có thể fail.

Một forwarder có thể dùng **SRS — Sender Rewriting Scheme** để viết lại envelope sender cho phù hợp luồng forwarding. Tuy nhiên, kết quả SPF sau rewrite có thể aligned với domain của forwarder thay vì Header From gốc; khi đó **DKIM aligned từ sender gốc** rất quan trọng đối với DMARC.

### 16.2. DKIM có thể giúp mail qua forwarding

Nếu forwarding không sửa những phần đã được DKIM ký, chữ ký gốc có thể vẫn pass. Vì vậy, triển khai DKIM aligned thường hữu ích khi SPF bị ảnh hưởng bởi việc chuyển tiếp.

Nhưng DKIM có thể fail nếu forwarding/list manager:
- thêm footer vào body;
- sửa subject;
- thay link tracking;
- chuyển đổi MIME;
- sửa các signed headers.

### 16.3. Mailing list có thể làm DMARC khó pass

Mailing list đôi khi giữ Header From của tác giả nhưng thay nội dung và gửi qua IP của list. Kết quả có thể:
- SPF pass cho list domain nhưng không aligned với From domain của tác giả;
- DKIM của tác giả fail vì list sửa body;
- DMARC fail nếu không còn cơ chế aligned nào pass.

Một số list chọn cách viết lại From hoặc điều chỉnh luồng gửi. Cách xử lý cần đánh giá trải nghiệm người nhận, quy tắc mailing list và bảo mật; không khuyến nghị tắt `p=reject` của toàn miền chỉ vì một luồng list chưa được thiết kế đúng.

### 16.4. ARC là gì?

**ARC — Authenticated Received Chain** có thể giúp các hệ thống trung gian truyền đạt lịch sử xác thực khi email bị forwarding/modification. Nhưng ARC **không đơn giản biến `dmarc=fail` thành `dmarc=pass`**. Receiver có thể dùng ARC như một tín hiệu trong chính sách riêng; việc tin ARC chain phụ thuộc đánh giá của receiver.

Không coi ARC là lý do để bỏ SPF, DKIM hoặc DMARC alignment ở hệ thống phát thư.

## 17. Deliverability không chỉ là SPF, DKIM và DMARC

Ba cơ chế này xác thực miền/danh tính, nhưng **không đảm bảo thư vào Inbox**.

Các yếu tố khác ảnh hưởng:
- IP/domain reputation;
- tần suất và độ ổn định của lưu lượng;
- tỷ lệ complaint, bounce và spam traps;
- lịch sử tương tác và mức độ người nhận mong đợi nội dung;
- danh sách opt-in/unsubscribe;
- chất lượng danh sách recipient;
- nội dung thư và các URL liên kết;
- PTR/rDNS và SMTP `HELO/EHLO` consistency theo yêu cầu provider;
- TLS, rate limit, chính sách receiving MTA;
- tình trạng mailbox hoặc suppression policy.

Một email có cả ba kết quả `pass` vẫn có thể bị xếp vào spam vì nội dung, reputation hoặc người nhận không mong đợi.

### 17.1. Tách authentication failure khỏi delivery failure

| Trạng thái | Ý nghĩa |
|---|---|
| `spf=fail` | SPF authorization không thành công cho identifier được đánh giá. |
| `dkim=fail` | Chữ ký DKIM được kiểm tra không pass. |
| `dmarc=fail` | Không có SPF/DKIM pass aligned với From. |
| SMTP `250 accepted` | SMTP relay đã nhận submission; không có nghĩa đã vào Inbox. |
| Provider `delivered` | Thường là mail server đích chấp nhận; không phải bằng chứng người dùng đã mở. |
| `bounced` | Provider/MTA báo không giao được. |
| `spam` / `quarantine` | Receiver/client phân loại thư theo chính sách riêng. |

Đừng cố “sửa deliverability” chỉ bằng thay DMARC `p=reject` thành `p=none` nếu vấn đề thực tế là reputation hoặc không có unsubscribe.

### 17.2. Dữ liệu vận hành cần theo dõi

Nên quan sát:
- SPF/DKIM/DMARC pass rate theo From domain và provider;
- mismatch giữa Header From, envelope sender và DKIM d=;
- report volume từ các IP lạ;
- SPF permerror/temperror;
- DKIM fail do selector, DNS hoặc body modification;
- bounce, complaint, suppression;
- SMTP submission failure và rate limiting;
- số email gửi từ từng domain/subdomain.

Sử dụng message key/attempt ID để tra cứu một email cụ thể, và DMARC aggregate reporting để phân tích **tình trạng xác thực ở cấp miền**.

## 18. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| SPF pass nhưng DMARC fail | Envelope MAIL FROM thuộc domain ngoài From; DKIM không aligned | Cấu hình custom MAIL FROM hoặc DKIM aligned. |
| DKIM pass nhưng DMARC fail | `d=` của signer là domain provider khác | Kích hoạt domain DKIM riêng/aligned. |
| SPF `permerror` | Hai SPF records hoặc quá nhiều DNS lookups | Hợp nhất một record đúng owner name, giảm lookup. |
| SPF record ở apex nhưng SPF vẫn fail | MAIL FROM dùng bounce subdomain | Công bố/ủy quyền SPF ở domain được đánh giá thật. |
| SPF pass ở môi trường dev, fail ở production | IP/relay khác nhau | Kiểm kê sender IP và provider config theo môi trường. |
| DKIM `selector not found` | DNS selector chưa tồn tại hoặc sai d=/s= | Kiểm tra `s._domainkey.d` và TTL. |
| DKIM fail sau khi thêm footer | Message bị sửa sau DKIM signing | Ký sau bước biến đổi hoặc dừng sửa phần đã ký. |
| DKIM fail sau rotation | Selector cũ bị xóa quá sớm hoặc key mismatch | Giữ overlap, kiểm tra phiên bản khóa. |
| DMARC fail chỉ ở forwarded mail | SPF không sống sót qua forwarding, DKIM không còn pass | Cải thiện DKIM, xem SRS/ARC/list behavior. |
| p=reject làm mail hợp lệ bị từ chối | Còn sender chưa có aligned SPF/DKIM | Quay lại kiểm kê nguồn, khắc phục và rollout có kiểm soát. |
| Không nhận DMARC aggregate reports | Receiver không gửi, rua sai, external authorization thiếu | Kiểm tra rua, mailbox, policy và yêu cầu domain ngoài. |
| SPF/DKIM/DMARC đều pass nhưng vào spam | Reputation, nội dung, complaint hoặc chính sách receiver | Điều tra deliverability ngoài authentication. |
| Spring SMTP AUTH thành công nhưng DKIM fail | SMTP login không quyết định DKIM signing | Kiểm tra provider domain verification và signer. |
| Return-Path header tự đặt nhưng SPF không đổi | Header không điều khiển SMTP envelope | Cấu hình MAIL FROM/bounce domain tại transport/provider. |
| Chỉ test MimeMessage unit nên không thấy DKIM | Provider ký sau khi nhận MIME | Gửi thử qua tuyến thật vào mailbox test và xem raw headers. |

## 19. Checklist triển khai cấp miền

### 19.1. Trước khi cấu hình

- [ ] Xác nhận domain/subdomain thuộc quyền quản lý của tổ chức.
- [ ] Liệt kê tất cả hệ thống gửi và owner.
- [ ] Xác định Header From của từng luồng.
- [ ] Xác định MAIL FROM/return-path domain thực tế.
- [ ] Xác định DKIM signing d=/selector của từng provider.
- [ ] Kiểm tra provider hỗ trợ custom domain authentication và bounce domain như thế nào.
- [ ] Bảo vệ SMTP credentials, DKIM private keys và quyền DNS write.

### 19.2. Khi công bố DNS

- [ ] SPF ở đúng owner name, một SPF policy hợp lệ tại mỗi name.
- [ ] Không vượt giới hạn SPF DNS lookup.
- [ ] DKIM TXT/CNAME theo chính xác selector/domain của provider.
- [ ] DMARC TXT ở đúng policy domain.
- [ ] Kiểm tra `p`, `sp`, `rua` và alignment mode.
- [ ] Nếu dùng external report address, hoàn tất authorization cần thiết.
- [ ] Theo dõi TTL và lưu lịch sử thay đổi.
- [ ] Không công khai private key DKIM.

### 19.3. Trước khi nâng lên p=reject

- [ ] Gửi test từ mọi nguồn gửi hợp lệ.
- [ ] Đối chiếu SPF `smtp.mailfrom` và DKIM `header.d` với Header From.
- [ ] Xác nhận DMARC pass trên receiver đáng tin cậy.
- [ ] Xem aggregate reports đủ để nhận diện nguồn gửi bị bỏ sót.
- [ ] Kiểm tra luồng forward/list quan trọng.
- [ ] Có owner, runbook, khả năng rollback và giám sát bounce.
- [ ] Không dựa vào một test mail đơn lẻ.

## 20. Bài tập thực hành

### Bài 1 — Phân biệt các định danh

Cho:

```text
From: billing@example.com
Reply-To: help@example.com
MAIL FROM:<bounce@bounces.example.com>
DKIM-Signature: ... d=example.com; s=tx1 ...
```

Hãy xác định domain SPF kiểm tra, domain DKIM dùng và domain làm trung tâm của DMARC. Giải thích vì sao Reply-To không tham gia alignment.

### Bài 2 — SPF tại bounce subdomain

Một SMTP provider gửi bằng `bounce@bounces.example.com` nhưng admin chỉ tạo SPF ở `example.com`. Hãy chỉ ra owner name cần kiểm tra và cách xác minh bằng `dig` hoặc `Resolve-DnsName`.

### Bài 3 — Hai SPF TXT records

Một domain có hai record `v=spf1`, một cho marketing và một cho transactional. Hãy giải thích rủi ro `permerror`, đề xuất một policy phù hợp hoặc tách MAIL FROM subdomains, đồng thời kiểm tra lookup budget.

### Bài 4 — DMARC relaxed versus strict

From domain là `example.com`. SPF pass cho `bounce.example.com` và DKIM pass với `d=mail.example.com`. Hãy xác định DMARC khi `aspf=r/adkim=r`, rồi khi cả hai chuyển sang `s`.

### Bài 5 — SPF pass, DKIM pass nhưng DMARC fail

Email có `From: alerts@example.com`, trong khi SPF và DKIM đều pass bằng domain `vendor.other.example`. Hãy giải thích vì sao DMARC fail và thiết kế custom DKIM signing domain.

### Bài 6 — Spring Boot sender

Viết cấu hình SMTP STARTTLS 587, hostname verification và envelope sender `bounce@bounces.example.com`; dùng `helper.setFrom("notices@example.com")`. Xác định phần nào Spring kiểm soát và phần nào cần cấu hình ở DNS/provider.

### Bài 7 — DKIM key rotation

Provider A đang ký bằng selector `old1`. Thiết kế các bước publish selector `new1`, chuyển signing, giữ overlap rồi retire khóa cũ; nêu nguy cơ xóa TXT cũ quá sớm.

### Bài 8 — Forwarding

Một thư SPF pass khi nhận đầu tiên, sau đó bị forward nên SPF fail ở hộp thư cuối. Nếu DKIM d= aligned vẫn pass, DMARC có thể đạt không? Giải thích khi forwarding làm sửa body.

### Bài 9 — Phân tích Authentication-Results

Cho kết quả:

```text
spf=pass smtp.mailfrom=outbound.provider.example
dkim=pass header.d=example.com
dmarc=pass header.from=example.com
```

Hãy xác định cơ chế nào giúp DMARC pass, mặc dù SPF không aligned.

### Bài 10 — Rollout DMARC

Tổ chức có ba hệ thống gửi: Spring Boot, CRM và helpdesk. Hãy lập kế hoạch `p=none`, kiểm kê nguồn, sửa alignment, theo dõi reports, rồi chuyển `quarantine` và `reject` mà không làm hỏng email hợp lệ.

### Bài 11 — DKIM và chỉnh sửa MIME

Một gateway thêm footer sau khi provider đã ký DKIM. Hãy giải thích vì sao `bh=`/signature có thể không còn pass và đề xuất vị trí ký phù hợp.

### Bài 12 — Ba cơ chế đều pass nhưng email vào spam

Hãy chỉ ra ít nhất năm yếu tố deliverability khác authentication và đề xuất metric theo dõi để tìm nguyên nhân.

## 21. Tổng kết

**SPF, DKIM và DMARC ở cấp miền** không phải ba cờ có thể bật toàn bộ trong Spring Mail. Chúng là sự phối hợp giữa **DNS owner name, SMTP envelope, outbound signing infrastructure, Header From và chính sách receiver**.

Hãy ghi nhớ:

1. **SPF** xác thực IP gửi cho domain được đánh giá từ SMTP envelope (`MAIL FROM`; đôi khi HELO), không trực tiếp xác thực Header From.
2. **DKIM** xác minh chữ ký với `d=` và public key dưới `s._domainkey.d`. Spring `MimeMessageHelper` không tự ký DKIM; signer thường ở SMTP provider/MTA.
3. **DMARC** gắn kết kết quả với Header From: **SPF pass + aligned hoặc DKIM pass + aligned** thì DMARC pass.
4. **SPF/DKIM pass nhưng không aligned vẫn có thể DMARC fail**. Vì vậy phải kiểm tra cả `smtp.mailfrom`, `header.d` và `header.from`.
5. Triển khai DNS đúng nơi: SPF của envelope domain, DKIM selector của signing domain, DMARC policy của From domain.
6. Bắt đầu DMARC bằng **kiểm kê nguồn và `p=none`**, dùng báo cáo để khắc phục trước khi tiến tới `quarantine` và `reject`.
7. Kiểm tra bằng DNS tools và **Authentication-Results của receiver đáng tin cậy**, không chỉ bằng kết quả `JavaMailSender.send(...)`.
8. SPF/DKIM/DMARC là nền tảng xác thực, nhưng **không bảo đảm Inbox placement**; reputation, bounces, complaints, nội dung và chính sách người nhận vẫn quyết định deliverability.

Khi các domain identities được cấu hình đúng và được giám sát liên tục, hệ thống Spring Mail có thể gửi thư bằng danh tính đáng tin cậy hơn, giảm nguy cơ giả mạo miền trong Header From và giúp nhóm vận hành chẩn đoán lỗi xác thực một cách có hệ thống.
