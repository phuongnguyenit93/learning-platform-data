# Chính sách lỗi khi không truy cập được nguồn kiểm tra thu hồi trong Java

> **Module:** Java 8 — **Mật mã ứng dụng**. Bài học giải quyết tình huống một ứng dụng cần xác minh trạng thái thu hồi chứng chỉ X.509 nhưng không thể truy cập nguồn kiểm tra. Trọng tâm là phân biệt **chứng chỉ đã bị thu hồi**, **được báo chưa thu hồi**, **không xác định được trạng thái**, **phản hồi sai** và **nguồn không thể truy cập**; lựa chọn chính sách hard-fail/soft-fail theo rủi ro; dùng `PKIXRevocationChecker` của Java 8; thiết kế fallback OCSP/CRL, timeout, cache, giám sát và kiểm thử. Các API được trình bày vẫn được hỗ trợ trên Java hiện hành.

## 1. Tình huống: máy chủ không truy cập được OCSP hoặc CRL

Một client nhận certificate X.509 của server. Chữ ký certificate đúng, thời hạn còn hiệu lực, hostname khớp và certificate chain dẫn tới trust anchor được tin cậy. Nhưng khi client muốn xác minh certificate chưa bị thu hồi, nó không kết nối được OCSP responder hoặc không tải được CRL.

Lúc này có hai câu hỏi khác nhau:

1. **Certificate có bị thu hồi không?** Đây là trạng thái bảo mật của certificate.
2. **Client có lấy được bằng chứng về trạng thái đó không?** Đây là tình trạng truy cập nguồn dữ liệu.

Mất kết nối không tự chứng minh certificate bị thu hồi; nhưng cũng **không chứng minh certificate còn an toàn**.

Ví dụ, một certificate bị lộ private key có thể đã bị CA thu hồi. Nếu OCSP server tạm thời không hoạt động, client không thể suy ra rằng certificate vẫn hợp lệ chỉ vì không nhận được câu trả lời.

Một chính sách cần xác định hành vi khi không thể kiểm tra:

- **Hard-fail / fail-closed:** nếu không xác định được trạng thái theo policy, từ chối xác thực.
- **Soft-fail / fail-open có giới hạn:** cho phép tiếp tục trong một số lỗi truy cập tạm thời đã được định nghĩa, đồng thời ghi nhận cảnh báo và rủi ro.
- **Retry / fallback:** thử lại có giới hạn hoặc chuyển sang nguồn kiểm tra khác trước khi quyết định.

Không có một lựa chọn đúng cho mọi ứng dụng. Quyết định phải dựa trên mức độ nhạy cảm của tài nguyên, khả năng chấp nhận rủi ro và yêu cầu availability.

## 2. Certificate revocation là một phần của PKIX validation

Một certificate X.509 có thể bị CA thu hồi trước ngày hết hạn. Các lý do thường gặp:

- Private key bị lộ hoặc nghi ngờ bị sao chép.
- Subject hoặc thông tin định danh không còn đáng tin.
- Certificate được cấp sai hoặc có lỗi trong quy trình phát hành.
- Chủ thể không còn được phép sử dụng certificate.
- CA cần thu hồi certificate vì một sự cố bảo mật.

Khi kiểm tra một certificate chain, ứng dụng còn phải xem xét:

1. Chữ ký của từng certificate và quan hệ issuer/subject.
2. Trust anchor và certificate path.
3. Thời hạn `notBefore`/`notAfter`.
4. Basic constraints, key usage, extended key usage và các policy liên quan.
5. Hostname/service identity trong TLS.
6. Thuật toán và key size còn được chấp nhận.
7. Trạng thái thu hồi theo policy.

**Revocation check không thay thế các bước khác.** Một certificate có trạng thái OCSP `good` vẫn có thể hết hạn, sai hostname, sai usage, không dẫn tới trust anchor hoặc dùng thuật toán bị cấm. Ngược lại, certificate path đúng về chữ ký và thời hạn vẫn có thể chứa certificate đã bị thu hồi.

### 2.1. GOOD không có nghĩa “mọi thứ đều đáng tin”

Trong OCSP, `good` có nghĩa responder báo không có thông tin cho thấy certificate bị thu hồi theo phạm vi/trạng thái được hỏi. Nó không thay thế toàn bộ PKIX validation, không chứng minh private key chưa từng bị lộ, cũng không phải bằng chứng độc lập rằng mọi thuộc tính của certificate đều hợp lệ.

### 2.2. Không truy cập được nguồn không phải là một trạng thái certificate

Hãy phân biệt:

~~~text
Certificate status:
    GOOD / REVOKED / UNKNOWN

Retrieval or validation result:
    RESPONSE_RECEIVED / NETWORK_UNAVAILABLE / INVALID_RESPONSE
~~~

`NETWORK_UNAVAILABLE` mô tả việc lấy dữ liệu thất bại. `UNKNOWN` là một kết quả trạng thái mà responder có thể trả về. Hai điều này không được gộp thành `GOOD`.

## 3. Hai cơ chế phổ biến: CRL và OCSP

### 3.1. CRL — Certificate Revocation List

CRL là danh sách certificate đã bị thu hồi, do CA hoặc CRL issuer được ủy quyền phát hành và ký số. Mỗi mục thường xác định certificate bằng serial number trong ngữ cảnh issuer.

Quy trình khái quát:

~~~text
Client
  |
  | tải CRL từ distribution point / repository
  v
CRL issuer
  |
  | CRL được ký số
  v
Client kiểm tra:
  - chữ ký và issuer của CRL
  - thisUpdate / nextUpdate
  - phạm vi và distribution point
  - serial number của certificate
  |
  +-- có trong CRL --> REVOKED
  |
  +-- không có trong CRL và CRL bao phủ đầy đủ --> không bị liệt kê là revoked
  |
  +-- CRL thiếu, cũ hoặc không xác minh được --> chưa có kết luận đáng tin
~~~

**Ưu điểm:**

- Có thể tải một lần rồi dùng để kiểm tra nhiều certificate do cùng issuer phát hành.
- Có thể lưu cache cục bộ và phân phối qua repository.
- Không cần gửi từng truy vấn certificate status riêng tới responder.

**Hạn chế:**

- CRL có thể lớn, nhất là CA phát hành nhiều certificate.
- CRL chỉ cập nhật theo chu kỳ; một lần thu hồi mới có thể chưa xuất hiện ngay trong CRL đang cache.
- Tải CRL có thể tốn băng thông và thời gian.
- Nếu CRL đã quá hạn hoặc không bao phủ certificate cần kiểm tra, không được coi kết quả là một bằng chứng hiện hành.

Theo RFC 5280, các trường `thisUpdate` và `nextUpdate` mô tả thời điểm phát hành và thời hạn dự kiến cho CRL tiếp theo. Ứng dụng phải xét freshness và phạm vi trước khi sử dụng kết quả.

### 3.2. OCSP — Online Certificate Status Protocol

OCSP cho phép client hỏi trạng thái một certificate thông qua responder.

~~~text
Client
  |
  | OCSP request (certificate identifier)
  v
OCSP responder
  |
  | signed OCSP response
  v
Client kiểm tra:
  - response có đúng certificate được hỏi không
  - chữ ký responder có hợp lệ và được ủy quyền không
  - response có còn fresh không
  - trạng thái GOOD / REVOKED / UNKNOWN
~~~

Các trạng thái chính trong RFC 6960:

| OCSP status | Ý nghĩa | Hành động thông thường |
| --- | --- | --- |
| `good` | Responder báo không có thông tin cho thấy certificate bị thu hồi | Có thể tiếp tục các bước PKIX khác |
| `revoked` | Certificate đã bị thu hồi hoặc đặt ở trạng thái thu hồi theo response | Từ chối certificate |
| `unknown` | Responder không xác định được trạng thái | Thử nguồn khác nếu policy cho phép; nếu vẫn unknown thì áp policy |

OCSP response là dữ liệu có chữ ký. Client phải kiểm tra chữ ký, danh tính/ủy quyền của responder, certificate identifier và thời gian hiệu lực. Không chấp nhận một response chỉ vì nhận được HTTP 200 hoặc nội dung parse được.

**Ưu điểm:**

- Trả lời theo từng certificate, thường giảm lượng dữ liệu phải tải so với CRL lớn.
- Có thể cập nhật trạng thái nhanh hơn chu kỳ phát hành CRL.
- Có thể cache response theo thời gian hợp lệ.

**Hạn chế:**

- Phụ thuộc mạng và khả năng phục vụ của responder.
- Client có thể tạo nhiều truy vấn khi có nhiều certificate hoặc nhiều kết nối.
- Cần xác minh chữ ký, responder authorization và freshness.
- Có thể tiết lộ cho responder certificate mà client đang kiểm tra, tùy kiến trúc và cách truy vấn.

### 3.3. OCSP và CRL có thể làm fallback cho nhau

Java PKIX revocation checker hỗ trợ cả hai cơ chế. Tài liệu API của `PKIXRevocationChecker` mô tả mặc định ưu tiên OCSP và CRL là fallback; `PREFER_CRLS` đổi thứ tự ưu tiên, còn `NO_FALLBACK` tắt fallback.

Tuy nhiên, cấu hình mặc định của **provider** cũng có vai trò. Với Oracle/SUN provider khi dùng cơ chế revocation mặc định, security property `ocsp.enable` mặc định là false; bảng cấu hình của Oracle mô tả CRL-only khi revocation bật nhưng OCSP chưa bật. Nếu bật `ocsp.enable=true`, OCSP được dùng và có thể fallback sang CRL khi gặp sự cố. Khi gắn `PKIXRevocationChecker` tường minh, hãy xem đúng contract của checker và provider đang chạy; không suy ra hành vi chỉ từ một property riêng lẻ.

### 3.4. Không fallback khi đã có kết luận REVOKED

Nếu một nguồn status hợp lệ, được xác thực và còn fresh xác nhận certificate đã bị thu hồi, việc nguồn khác tạm thời trả `good` hoặc không truy cập được không nên được dùng để hạ mức cảnh báo và cho phép certificate đi qua. Khi các nguồn mâu thuẫn, áp dụng chính sách bảo thủ, ghi nhận bằng chứng và điều tra freshness/provider configuration.

## 4. Phân loại kết quả trước khi quyết định

Đây là phần quan trọng nhất của bài. Không nên chỉ có hai trạng thái boolean `valid` và `invalid` cho mọi lỗi.

| Kết quả | Ví dụ | Ý nghĩa bảo mật | Hướng xử lý |
| --- | --- | --- | --- |
| GOOD | OCSP response hợp lệ báo good; CRL mới và bao phủ certificate | Có bằng chứng status chưa bị thu hồi trong phạm vi kiểm tra | Tiếp tục các bước certificate validation khác |
| REVOKED | OCSP/CRL hợp lệ chỉ ra serial đã bị thu hồi | Certificate không được chấp nhận | Reject, không soft-fail |
| UNKNOWN | OCSP responder không biết trạng thái certificate | Chưa có kết luận | Thử nguồn khác theo policy; nếu vẫn unknown thì không tự đổi thành good |
| NETWORK_UNAVAILABLE | DNS, connect, timeout, proxy hoặc route lỗi | Không lấy được bằng chứng status | Retry/fallback; sau đó hard-fail hoặc soft-fail có giới hạn |
| TRY_LATER / INTERNAL_ERROR | OCSP responder tạm thời không xử lý được request | Responder báo lỗi tạm thời | Có thể retry/fallback; Java SOFT_FAIL có điều kiện cụ thể |
| INVALID_RESPONSE | Sai chữ ký, sai certificate identifier, response không fresh, parse lỗi | Không có bằng chứng hợp lệ | Reject hoặc thử nguồn tin cậy khác; không bỏ qua như lỗi mạng |
| UNAUTHORIZED | Responder không cho phép request hoặc không thể trả lời có thẩm quyền | Chưa có bằng chứng status | Kiểm tra cấu hình/quyền; không mặc định soft-fail |
| STALE_DATA | CRL/OCSP response đã quá hạn | Không còn đủ cơ sở tin freshness | Lấy dữ liệu mới hoặc áp policy không xác định |

### 4.1. UNKNOWN khác NETWORK_UNAVAILABLE

- `UNKNOWN` là responder đã trả lời nhưng không biết trạng thái.
- `NETWORK_UNAVAILABLE` là client không nhận được response phù hợp do lỗi truy cập.
- `INVALID_RESPONSE` là client nhận được dữ liệu nhưng không thể tin hoặc không thể xác minh.

Đây là ba trường hợp khác nhau về nguyên nhân và mức tin cậy. Một chính sách soft-fail không nên biến mọi trường hợp thành “chấp nhận”.

### 4.2. Stale không phải Good

Một OCSP response có `thisUpdate` quá xa hiện tại hoặc `nextUpdate` đã qua có thể không còn đáng tin. Tương tự, CRL cũ không thể mặc định là CRL hiện hành.

Không dùng quy tắc “đã từng có response good thì cache mãi”. Nếu cache hết hạn, trạng thái phải được xem xét lại theo policy và nguồn cập nhật.

### 4.3. Lỗi chứng chỉ không phải lỗi nguồn status

Một certificate sai chữ ký, hết hạn, không khớp hostname hoặc không dẫn tới trust anchor phải bị từ chối dù OCSP/CRL server có sẵn và trả good. Soft-fail chỉ điều chỉnh phần **không lấy được revocation status theo các điều kiện được định nghĩa**, không làm nới lỏng các kiểm tra certificate khác.

## 5. Hard-fail, soft-fail và fail-open/fail-closed

### 5.1. Hard-fail (fail-closed)

Hard-fail nghĩa là không thể xác minh trạng thái thu hồi thì không chấp nhận certificate cho hoạt động đang bảo vệ.

~~~text
GOOD + các bước PKIX khác hợp lệ --> ACCEPT
REVOKED                         --> REJECT
UNKNOWN không giải quyết được   --> REJECT
NETWORK_UNAVAILABLE             --> REJECT
INVALID_RESPONSE                --> REJECT
STALE_DATA                      --> REJECT hoặc lấy nguồn mới; không dùng dữ liệu cũ
~~~

Ưu điểm:

- Không mở đường cho certificate đã bị thu hồi chỉ vì nguồn kiểm tra mất kết nối.
- Chính sách rõ ràng, dễ audit.
- Phù hợp khi xác thực có rủi ro cao và yêu cầu revocation checking là bắt buộc.

Đánh đổi:

- Một outage của CA/OCSP/CRL, DNS hoặc network egress có thể làm gián đoạn truy cập hợp lệ.
- Cần vận hành nguồn dữ liệu, proxy, timeout và fallback tốt để giảm false outage.

### 5.2. Soft-fail có giới hạn

Soft-fail có thể cho phép tiếp tục khi **không thể lấy status vì một số lỗi truy cập tạm thời**. Nó không có nghĩa chấp nhận mọi certificate không xác định.

Một policy ở tầng ứng dụng có thể mô tả:

~~~text
GOOD                  --> ACCEPT
REVOKED               --> REJECT
NETWORK ERROR          --> thử nguồn fallback
OCSP internalError /
tryLater               --> retry/fallback
mọi nguồn vẫn lỗi mạng  --> có thể ACCEPT_WITH_WARNING nếu policy cho phép
UNKNOWN                --> không tự đổi thành GOOD
INVALID RESPONSE       --> REJECT hoặc nguồn tin cậy khác
~~~

Java `PKIXRevocationChecker.Option.SOFT_FAIL` có hợp đồng cụ thể: cho phép revocation check thành công khi status không xác định được do lỗi mạng lấy CRL/OCSP hoặc một số OCSP responder errors như `internalError`/`tryLater`. Khi fallback vẫn bật, Java API quy định check chỉ được phép thành công nếu **cả hai cơ chế** đều thất bại vì một trong các điều kiện được cho phép. Nếu `NO_FALLBACK` được đặt, hành vi fallback thay đổi.

**SOFT_FAIL không bỏ qua kết quả REVOKED, không làm response sai chữ ký trở nên hợp lệ, và không phải chế độ “trust all”.**

### 5.3. Fail-open là quyết định chấp nhận rủi ro

Fail-open có thể giúp hệ thống duy trì availability trong một outage ngắn, nhưng mở rộng thời gian một certificate đã bị thu hồi vẫn có thể được chấp nhận. Rủi ro tăng nếu private key bị xâm phạm, certificate được sử dụng cho quyền truy cập nhạy cảm hoặc nguồn revocation outage kéo dài.

Nếu sản phẩm chọn soft-fail, nên xác định:

- Những lỗi nào được xem là transient và được phép bỏ qua.
- Những loại certificate/service nào có thể dùng soft-fail.
- Giới hạn thời gian cho phép tiếp tục khi status không xác định.
- Số lần retry, timeout và fallback.
- Cảnh báo, audit và điều kiện chuyển về hard-fail.
- Ai sở hữu quyết định chấp nhận rủi ro và cách phê duyệt thay đổi.

Không đặt soft-fail toàn cục chỉ để giảm lỗi kết nối.

### 5.4. Bảng lựa chọn theo rủi ro

| Ngữ cảnh | Chính sách thường phù hợp để đánh giá | Lý do |
| --- | --- | --- |
| Thanh toán, ký giao dịch quan trọng, truy cập đặc quyền | Ưu tiên hard-fail khi không xác định status | Hậu quả chấp nhận certificate đã bị thu hồi cao |
| Xác thực dịch vụ nội bộ có nguồn status được quản lý | Hard-fail hoặc soft-fail rất hẹp, có giới hạn và giám sát | Có thể thiết kế nguồn HA, cache và đường mạng kiểm soát |
| Tác vụ không nhạy cảm, availability quan trọng | Có thể cân nhắc soft-fail cho lỗi mạng tạm thời | Rủi ro có thể được chấp nhận nếu phạm vi và thời gian được giới hạn |
| Xác minh chữ ký/tài liệu cần audit dài hạn | Áp chính sách status theo thời điểm ký và bằng chứng lưu trữ | Có thể cần historical validation, timestamp và archival evidence |

Đây là hướng đánh giá rủi ro, không phải quy tắc bắt buộc cho mọi ngành. Phải xét tiêu chuẩn, hợp đồng, quy định và kiến trúc thực tế của hệ thống.

## 6. Java 8: PKIXRevocationChecker và các Option

`java.security.cert.PKIXRevocationChecker` có từ Java 8, là checker dùng thuật toán PKIX để kiểm tra trạng thái thu hồi qua OCSP/CRL.

Các option:

| Option | Tác dụng | Lưu ý |
| --- | --- | --- |
| `SOFT_FAIL` | Bỏ qua một số lỗi mạng và OCSP responder errors được chỉ định | Không bỏ qua revoked hoặc mọi loại lỗi |
| `PREFER_CRLS` | Ưu tiên CRL thay vì OCSP | Fallback phụ thuộc provider/option |
| `NO_FALLBACK` | Tắt cơ chế fallback | Cần hiểu ảnh hưởng khi nguồn ưu tiên không truy cập được |
| `ONLY_END_ENTITY` | Chỉ kiểm tra end-entity certificate | Có thể bỏ qua intermediate CA; chỉ dùng khi policy cho phép |

### 6.1. Lấy checker từ PKIX CertPathValidator

~~~java
CertPathValidator validator =
        CertPathValidator.getInstance("PKIX");

PKIXRevocationChecker checker =
        (PKIXRevocationChecker) validator.getRevocationChecker();
~~~

Đây là đoạn Java 8. PKIX provider cung cấp checker tương ứng. Nếu một provider không hỗ trợ API/algorithm cần thiết, phải xử lý lỗi cấu hình hoặc chọn provider phù hợp; không âm thầm tắt revocation.

### 6.2. Cấu hình SOFT_FAIL

~~~java
checker.setOptions(EnumSet.of(
        PKIXRevocationChecker.Option.SOFT_FAIL));
~~~

Đoạn này chỉ cấu hình option. Nó chưa xác minh certificate nào và cũng chưa tạo ra một quyết định nghiệp vụ. Việc thực thi xảy ra khi checker được gắn vào `PKIXParameters` hoặc `PKIXBuilderParameters` và parameters được truyền vào validator/builder.

### 6.3. Ưu tiên CRL và giữ fallback

~~~java
checker.setOptions(EnumSet.of(
        PKIXRevocationChecker.Option.PREFER_CRLS));
~~~

Cấu hình này ưu tiên CRL theo hợp đồng checker. Không đặt `NO_FALLBACK` nếu policy muốn provider có thể thử cơ chế còn lại. Chi tiết fallback của provider nên được kiểm thử với certificate, CRL và OCSP endpoint thực tế.

### 6.4. Tắt fallback là quyết định có chủ đích

~~~java
checker.setOptions(EnumSet.of(
        PKIXRevocationChecker.Option.PREFER_CRLS,
        PKIXRevocationChecker.Option.NO_FALLBACK));
~~~

Khi đó, nếu nguồn CRL ưu tiên không truy cập được, provider không chuyển sang OCSP. Đây có thể là lựa chọn trong môi trường chỉ chấp nhận một nguồn status được kiểm soát, nhưng có thể giảm availability.

### 6.5. ONLY_END_ENTITY không phải tối ưu mặc định

~~~java
checker.setOptions(EnumSet.of(
        PKIXRevocationChecker.Option.ONLY_END_ENTITY));
~~~

Option này chỉ kiểm tra revocation của certificate đầu cuối. Certificate intermediate CA cũng có thể bị thu hồi; bỏ qua nó có thể tạo ra lỗ hổng policy. Chỉ dùng khi mô hình trust và quy định của ứng dụng cho phép rõ ràng.

### 6.6. Kết hợp options

~~~java
checker.setOptions(EnumSet.of(
        PKIXRevocationChecker.Option.PREFER_CRLS,
        PKIXRevocationChecker.Option.SOFT_FAIL));
~~~

Đây là ví dụ kết hợp ưu tiên CRL và soft-fail. Nó **không** có nghĩa CRL không truy cập được thì luôn accept ngay; khi fallback còn bật, Java API quy định SOFT_FAIL chỉ cho phép check thành công sau khi cả CRL và OCSP đều thất bại vì những lý do được liệt kê.

## 7. Gắn checker vào PKIXParameters và validate certificate path

Đoạn sau là **method fragment** cho một ứng dụng đã có:

- `CertPath path`: certificate chain cần xác minh.
- `Set<TrustAnchor> trustAnchors`: trust anchors đã được ứng dụng quản lý.
- Provider PKIX hỗ trợ revocation checker.

~~~java
CertPathValidator validator =
        CertPathValidator.getInstance("PKIX");

PKIXRevocationChecker checker =
        (PKIXRevocationChecker) validator.getRevocationChecker();

checker.setOptions(EnumSet.of(
        PKIXRevocationChecker.Option.SOFT_FAIL));

PKIXParameters params = new PKIXParameters(trustAnchors);

// Gắn checker trước khi validate.
params.addCertPathChecker(checker);

// Custom PKIXRevocationChecker vẫn được dùng khi được gắn vào params.
params.setRevocationEnabled(false);

CertPathValidatorResult result =
        validator.validate(path, params);
~~~

**Lưu ý quan trọng:** Khi một `PKIXRevocationChecker` được thêm vào `PKIXParameters`, checker được clone. Vì vậy hãy cấu hình tất cả option trước khi gọi `addCertPathChecker`; sửa object ban đầu sau đó không thay đổi checker đã được thêm. Checker cũng không thread-safe theo hợp đồng API; không chia sẻ một instance mutable cho nhiều validation chạy song song.

### 7.1. Vì sao ví dụ đặt setRevocationEnabled(false)?

Khi một `PKIXRevocationChecker` được thêm vào parameters, nó được dùng để kiểm tra revocation bất kể cờ `RevocationEnabled`. Ví dụ Oracle đặt false để không chạy thêm cơ chế mặc định của provider song song với custom checker. **False ở đây không vô hiệu hóa checker đã gắn.**

Nếu không gắn checker tường minh, `PKIXParameters` có default revocation flag true; provider mặc định quyết định cơ chế thực tế theo cấu hình của nó.

### 7.2. Validate path không chỉ gọi checker

`validator.validate(path, params)` thực hiện PKIX certification path validation với các kiểm tra tương ứng. Nếu certificate path không hợp lệ vì chữ ký, trust anchor, thời hạn, critical extensions hoặc revocation theo policy, method ném `CertPathValidatorException`.

Không bắt mọi exception rồi trả “valid”. Cần phân loại nguyên nhân và giữ failure semantics của certificate validation.

### 7.3. Tích hợp với CertPathBuilder

Nếu ứng dụng cần vừa tìm vừa xây dựng certificate path, có thể cấu hình `PKIXRevocationChecker` trên `PKIXBuilderParameters` rồi truyền vào `CertPathBuilder.build`. Đây là một đường khác với việc validate một `CertPath` đã dựng sẵn.

### 7.4. Kiểm soát vòng đời checker

- Tạo checker cho từng cấu hình/validation context phù hợp.
- Cấu hình options và OCSP responder trước khi add vào parameters.
- Không thay đổi checker sau khi đã add.
- Không share checker mutable giữa threads.
- Ghi nhận exception/metric soft-fail theo provider và lifecycle thực tế.
- Kiểm tra behavior của đúng JDK/provider triển khai, không chỉ dựa trên một môi trường development.

`getSoftFailExceptions()` là API cung cấp danh sách exception được bỏ qua khi dùng SOFT_FAIL. Tuy nhiên, do parameters clone checker khi thêm, không giả định object ban đầu bạn giữ luôn là instance thực thi nội bộ. Thiết kế telemetry theo API/provider lifecycle và xác minh bằng integration test.

## 8. Phân biệt explicit PKIXRevocationChecker với cấu hình mặc định của Oracle provider

Đây là chỗ dễ cấu hình sai vì có nhiều lớp cấu hình.

### 8.1. Khi dùng explicit PKIXRevocationChecker

Tài liệu Java SE mô tả checker hỗ trợ OCSP và CRL, mặc định ưu tiên OCSP rồi fallback sang CRL. Có thể thay đổi bằng `PREFER_CRLS` hoặc tắt fallback bằng `NO_FALLBACK`.

### 8.2. Khi dùng Oracle/SUN provider default revocation mechanism

Tài liệu Oracle mô tả:

- `PKIXParameters` mặc định có revocation enabled.
- Security property `ocsp.enable` mặc định false.
- Nếu revocation bật và OCSP chưa bật, cơ chế mặc định của provider sử dụng CRL.
- Khi OCSP được bật và có lỗi phù hợp, provider có thể fallback sang CRL.
- Nếu OCSP trả lời rõ certificate revoked hoặc không revoked, provider không fallback chỉ vì muốn thử một nguồn khác.

`ocsp.enable` là **security property**, không phải một boolean mà bạn nên tự đoán từ tên host. Nó có thể được cấu hình trong `java.security` hoặc qua `Security.setProperty` theo quy tắc runtime.

### 8.3. Đừng trộn các cấu hình mà không hiểu provider

Một ứng dụng có thể đồng thời có:

1. Default revocation behavior của PKIX provider.
2. Custom `PKIXRevocationChecker`.
3. TLS/JSSE revocation configuration.
4. OCSP responder URL và CRL distribution point trong certificate.

Chỉ bật một property không chứng minh toàn bộ đường validation đang dùng đúng policy. Hãy xác định code path nào thực sự được gọi và test nó bằng chain/response cụ thể.

## 9. TLS và OCSP: cấu hình cần đúng tầng

Certificate revocation checking thường xuất hiện trong TLS handshake. Tuy nhiên, một chương trình có thể dùng `CertPathValidator` trực tiếp hoặc dùng JSSE `TrustManager`; cấu hình hai đường này không hoàn toàn giống nhau.

### 9.1. Client-driven OCSP trong Java 8

Oracle ghi nhận hỗ trợ client-driven OCSP cho TLS từ **JDK 8u261**. Do đó, “Java 8” ở đây phải chỉ rõ update level; không giả định mọi bản JDK 8 cũ đều có cùng behavior TLS.

Theo hướng dẫn JSSE của Oracle, cần bật revocation checking và OCSP tương ứng. Cấu hình mặc định không nên bị hiểu là đã bật OCSP chỉ vì ứng dụng đang dùng HTTPS.

### 9.2. OCSP stapling

Với stapling, server gửi OCSP response đã lấy từ responder cùng handshake. Client vẫn phải xác minh response, chữ ký, certificate identifier và freshness; việc server gửi kèm response không tự làm response đáng tin.

OCSP stapling có thể giảm việc mỗi client trực tiếp truy cập responder, nhưng không xóa nhu cầu xử lý response thiếu, stale, invalid hoặc không có stapled status.

### 9.3. Không sửa lỗi revocation bằng TrustManager trust-all

Đây là phản ví dụ nghiêm trọng:

~~~java
// PHẢN VÍ DỤ: không dùng TrustManager chấp nhận mọi certificate.
TrustManager[] trustAll = new TrustManager[] {
    new X509TrustManager() {
        public X509Certificate[] getAcceptedIssuers() {
            return new X509Certificate[0];
        }
        public void checkClientTrusted(
                X509Certificate[] chain, String authType) {
        }
        public void checkServerTrusted(
                X509Certificate[] chain, String authType) {
        }
    }
};
~~~

Đoạn trên bỏ qua kiểm tra certificate chain, không phải giải pháp xử lý OCSP outage. Không thay trust validation bằng một trust manager rỗng, không tắt hostname verification để vượt qua lỗi status, và không catch exception rồi mặc định thành success.

## 10. Timeout, retry và fallback khi nguồn không truy cập được

### 10.1. Timeout kết nối và timeout đọc là hai giới hạn khác nhau

- **Connect timeout:** thời gian tối đa để thiết lập kết nối tới OCSP/CRL endpoint.
- **Read timeout:** thời gian tối đa chờ dữ liệu sau khi đã kết nối.

Nếu chỉ có connect timeout mà không có read timeout, một kết nối đã mở nhưng không trả dữ liệu có thể giữ tài nguyên lâu hơn dự kiến.

### 10.2. Oracle JDK hiện hành có các timeout properties cho CRL/OCSP

Tài liệu Oracle JDK 26 liệt kê các system properties provider-specific:

| Property | Tác dụng | Default trong tài liệu Oracle JDK 26 |
| --- | --- | --- |
| `com.sun.security.ocsp.timeout` | OCSP connect timeout | 15 giây |
| `com.sun.security.ocsp.readtimeout` | OCSP read timeout | Theo connect timeout |
| `com.sun.security.crl.timeout` | CRL connect timeout | 15 giây |
| `com.sun.security.crl.readtimeout` | CRL read timeout | 15 giây |
| `com.sun.security.cert.timeout` | Kết nối liên quan AIA của certificate | 15 giây |
| `com.sun.security.cert.readtimeout` | Đọc dữ liệu liên quan AIA | 15 giây |

Đây là các thuộc tính của implementation Oracle/SUN, **không phải tất cả đều là API portable của Java SE**. Kiểm tra đúng JDK/provider trong production trước khi cấu hình.

Giá trị 0 trong các property timeout được tài liệu Oracle mô tả là không giới hạn thời gian. Không dùng timeout vô hạn cho một service nhận request từ mạng; một endpoint treo có thể chiếm thread và làm cạn tài nguyên.

### 10.3. Retry phải có giới hạn

Một chiến lược vận hành có thể gồm:

1. Một lần request tới nguồn ưu tiên.
2. Nếu gặp lỗi tạm thời, chờ ngắn với backoff/jitter.
3. Thử lại theo giới hạn cấu hình.
4. Chuyển sang nguồn fallback nếu policy/provider hỗ trợ.
5. Nếu vẫn không xác định được, áp hard-fail hoặc soft-fail đã phê duyệt.

Không retry vô hạn. Không gửi hàng trăm request cùng lúc khi OCSP responder vừa hồi phục; dùng bounded concurrency và backoff để tránh tạo thêm tải.

### 10.4. Không retry khi đã có kết quả REVOKED

Một response REVOKED hợp lệ là kết luận bảo mật, không phải lỗi transport. Không retry để hy vọng nhận được GOOD rồi bỏ qua revoked response. Nếu dữ liệu giữa các nguồn mâu thuẫn, ghi nhận và điều tra freshness, issuer, certificate identifier và thời điểm response.

### 10.5. Phân biệt lỗi DNS, proxy, firewall và responder

Khi không kết nối được, log đủ thông tin vận hành để phân loại:

- DNS lookup thất bại.
- TCP connection timeout/refused.
- TLS/proxy/network egress lỗi nếu endpoint dùng HTTPS hoặc môi trường yêu cầu proxy.
- Read timeout.
- OCSP responder trả tryLater/internalError.
- HTTP status hoặc response ASN.1 không hợp lệ.
- Chứng thư responder không xác minh được.

Không ghi token nhạy cảm hoặc toàn bộ dữ liệu certificate chain vào log công khai; giữ serial/issuer/endpoint và mã lỗi theo chính sách audit.

## 11. Freshness và cache: không dùng status cũ vô thời hạn

### 11.1. OCSP response có thời gian hiệu lực

Các trường thời gian quan trọng trong OCSP:

- `thisUpdate`: thời điểm gần nhất responder biết status là đúng.
- `nextUpdate`: thời điểm mà trước hoặc tại đó thông tin mới hơn sẽ có.
- `producedAt`: thời điểm response được tạo/ký.
- `revocationTime`: thời điểm thu hồi nếu status revoked.

Client phải kiểm tra response có đúng certificate và còn fresh theo policy. Response có `nextUpdate` trong quá khứ hoặc `thisUpdate` ở tương lai so với clock hợp lệ có thể không đáng tin.

### 11.2. CRL cũng có thisUpdate và nextUpdate

CRL phải được xác minh chữ ký, issuer, phạm vi và freshness. Không dùng CRL hết hạn như một kết quả GOOD chỉ vì serial chưa xuất hiện trong danh sách.

### 11.3. Cache phải theo issuer và certificate identity

Không cache theo serial number đơn lẻ: serial number chỉ có nghĩa trong ngữ cảnh issuer. Cache key nên nhận diện đúng certificate/issuer theo dữ liệu định danh phù hợp.

### 11.4. Cache GOOD có hạn sử dụng

Một status GOOD tại thời điểm T không đảm bảo certificate vẫn chưa bị thu hồi tại T+1. Cache cần tuân thủ thời gian hiệu lực của response, freshness policy và giới hạn staleness được phê duyệt. Không tự gia hạn status bằng cách bỏ qua `nextUpdate`.

### 11.5. Cache REVOKED cần thận trọng

Một trạng thái revoked đã xác minh phải được xử lý bảo thủ. Không xóa cache revoked chỉ vì một request khác thất bại hoặc một nguồn khác không có dữ liệu. Nếu có thay đổi status hợp lệ theo quy trình CA (ví dụ release khỏi certificateHold trong CRL delta), xử lý theo semantics của RFC và provider, không tự sửa cache bằng logic ad hoc.

### 11.6. Đồng hồ hệ thống là một dependency bảo mật

Clock sai có thể khiến client đánh giá sai freshness hoặc thời gian hiệu lực. Đồng bộ thời gian đáng tin cậy, giám sát clock drift và kiểm thử clock skew là một phần của vận hành PKI.

## 12. Thiết kế quyết định theo policy thay vì catch-all exception

Một lớp nghiệp vụ nên phân biệt kết quả kiểm tra trước khi quyết định.

~~~text
                 Kiểm tra certificate path
                           |
                           v
                Thu thập revocation status
                           |
           +---------------+----------------+
           |               |                |
         GOOD           REVOKED          Không có kết luận
           |               |                |
           v               v                v
     PKIX checks       REJECT         Phân loại nguyên nhân
     tiếp tục                              |
                               +------------+-------------+
                               |            |             |
                           NETWORK       UNKNOWN       INVALID
                               |            |             |
                         Retry/fallback  Try source   Reject / source
                               |         khác theo     tin cậy khác
                               |         policy
                               v
                       Còn không truy cập?
                               |
                    +----------+----------+
                    |                     |
                 HARD-FAIL             SOFT-FAIL
                    |                     |
                  REJECT         Accept with warning
                                  chỉ khi policy cho phép
~~~

Sơ đồ này mô tả policy ứng dụng. Provider PKIX thực tế có thể xử lý OCSP/CRL fallback nội bộ; không nên chạy thêm một lớp truy vấn khác mà không hiểu thứ tự và semantics của nó.

### 12.1. Trả về kết quả có ý nghĩa

Thay vì một boolean đơn giản, có thể dùng một enum/domain result:

~~~java
enum RevocationDecision {
    GOOD,
    REVOKED,
    UNKNOWN,
    UNAVAILABLE,
    INVALID_RESPONSE
}
~~~

Đây là **mô hình nghiệp vụ minh họa**, không phải enum có sẵn trong Java SE. Nó giúp code gọi phân biệt trạng thái, tránh trả true chỉ vì không bắt được exception.

### 12.2. Tách quyết định status khỏi quyết định availability

Một hàm xác định status có thể trả GOOD/REVOKED/UNKNOWN. Một policy khác quyết định nếu UNAVAILABLE thì reject hay soft-fail. Giữ hai bước riêng giúp review security rõ hơn và test từng phần độc lập.

### 12.3. Không biến lỗi thành null rồi tiếp tục

~~~java
// PHẢN VÍ DỤ:
try {
    return checkRevocation(certificate);
} catch (Exception ex) {
    return null; // Caller có thể hiểu nhầm là "không có lỗi".
}
~~~

Đoạn này làm mất nguyên nhân và tạo một trạng thái không rõ nghĩa. Trả result type rõ ràng hoặc ném exception có phân loại phù hợp; caller phải có policy tường minh cho UNAVAILABLE/UNKNOWN.

## 13. Giám sát và vận hành khi revocation source gián đoạn

Soft-fail chỉ an toàn khi người vận hành biết nó đang xảy ra. Một hệ thống nên theo dõi:

1. Số lần OCSP request thành công/thất bại.
2. Số lần CRL fetch thành công/thất bại.
3. Tỷ lệ fallback từ OCSP sang CRL.
4. Số lần status UNKNOWN.
5. Số lần response stale hoặc invalid.
6. Số lần SOFT_FAIL bỏ qua lỗi mạng.
7. Latency p50/p95/p99 của kiểm tra revocation.
8. Số lần hard-fail làm từ chối xác thực.
9. Tuổi CRL/OCSP cache và thời gian còn lại đến nextUpdate.
10. Endpoint nào thường timeout, DNS/proxy/firewall nào lỗi.

### 13.1. Cảnh báo soft-fail phải được nhìn thấy

Không ghi một dòng log debug rồi quên. Khi certificate được chấp nhận dù revocation status chưa xác định do lỗi mạng, nên tạo metric/counter và log có context. Nếu tỷ lệ soft-fail tăng, cần alert theo ngưỡng và thời gian.

### 13.2. Không log quá nhiều mỗi lần retry

Một lỗi endpoint lặp lại trên hàng nghìn requests có thể tạo log flood. Dùng rate-limited logging, aggregate metrics và correlation id để vừa quan sát được outage vừa tránh làm cạn log pipeline.

### 13.3. Circuit breaker phải giữ nguyên security semantics

Circuit breaker có thể ngừng gọi một responder đang lỗi để giảm tải. Nhưng trạng thái circuit open **không phải GOOD**. Khi circuit open, policy vẫn phải quyết định hard-fail, fallback nguồn khác hoặc soft-fail đã được phê duyệt.

### 13.4. Đường mạng đến CA/OCSP/CRL là một phần của hệ thống

Vận hành cần kiểm tra DNS, proxy, firewall, egress allowlist, TLS trust của endpoint và khả năng truy cập các URI trong certificate extensions. Một thay đổi network policy có thể làm certificate validation thất bại dù certificate không thay đổi.

## 14. Kiểm thử chính sách lỗi

Không nên chỉ test trường hợp OCSP server chạy bình thường. Một bộ test tối thiểu nên có:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| OCSP GOOD, response hợp lệ và fresh | Revocation check pass |
| OCSP REVOKED | Reject |
| OCSP UNKNOWN | Thử nguồn khác theo policy; không tự accept |
| OCSP connect timeout, CRL GOOD và fresh | Có thể pass sau fallback |
| OCSP timeout, CRL cũng timeout, hard-fail | Reject |
| OCSP timeout, CRL cũng timeout, soft-fail bật | Chỉ có thể pass nếu lỗi thuộc điều kiện SOFT_FAIL và provider xử lý đúng |
| OCSP internalError/tryLater | Retry/fallback; xử lý SOFT_FAIL theo contract |
| Response chữ ký sai | Reject hoặc nguồn tin cậy khác; không coi là network error |
| Response cho sai certificate identifier | Reject |
| Response stale | Lấy nguồn mới hoặc áp policy unresolved |
| CRL signature sai | Reject |
| CRL hết nextUpdate | Không coi là dữ liệu hiện hành |
| Certificate hết hạn | Reject dù OCSP GOOD |
| Intermediate certificate revoked | Reject nếu policy kiểm tra toàn chain |
| Hostname sai | TLS identity validation reject dù revocation GOOD |
| DNS/proxy/firewall lỗi | Phân loại là retrieval failure |
| Clock lệch lớn | Kiểm tra freshness thất bại hoặc cảnh báo phù hợp |
| Nhiều requests cùng lúc | Không retry vô hạn hoặc làm cạn thread |
| Provider/JDK khác nhau | Xác minh behavior fallback và timeout theo runtime |
| Soft-fail được sử dụng | Có metric, log và cảnh báo |

### 14.1. Test riêng status và transport

Tách mock OCSP/CRL responder để có thể tạo status GOOD/REVOKED/UNKNOWN và các lỗi transport. Nếu chỉ mock HTTP timeout, bạn chưa kiểm thử semantics của status UNKNOWN hoặc chữ ký response.

### 14.2. Test fallback theo thứ tự

Ép nguồn ưu tiên lỗi và nguồn còn lại trả GOOD/REVOKED/UNKNOWN. Kiểm tra đúng thứ tự provider đã cấu hình. Với `PREFER_CRLS`, xác minh CRL được ưu tiên theo provider thực tế; với `NO_FALLBACK`, xác minh không gọi nguồn thứ hai.

### 14.3. Test stale cache

Tạo CRL/OCSP response có `nextUpdate` ở quá khứ và response mới hơn. Xác minh code không sử dụng response stale như bằng chứng GOOD chỉ vì nó vẫn có chữ ký hợp lệ.

### 14.4. Test certificate path khác với test revocation source

Dùng một chain hợp lệ và một chain sai chữ ký/trust anchor/hostname để chứng minh soft-fail không làm các bước validation khác pass.

## 15. Ví dụ Java 8 chạy độc lập: cấu hình checker và mô phỏng policy

Chương trình sau có hai mục tiêu rõ ràng:

1. Lấy `PKIXRevocationChecker` từ PKIX provider và cấu hình `SOFT_FAIL` thật bằng Java API.
2. Kiểm thử một **policy decision function** với các kết quả mô phỏng: GOOD, REVOKED, UNKNOWN, lỗi mạng sau fallback, tryLater và invalid response.

Chương trình **không gửi OCSP request hoặc tải CRL thật**, vì cần certificate chain, responder/repository và network fixture. Nó chứng minh API có sẵn trên runtime và kiểm tra logic quyết định của ứng dụng; integration test thật phải dùng test CA/OCSP/CRL riêng.

Lưu thành **RevocationPolicyDemo.java**:

~~~java
import java.security.cert.CertPathValidator;
import java.security.cert.PKIXRevocationChecker;
import java.util.EnumSet;

public final class RevocationPolicyDemo {
    enum Status {
        GOOD,
        REVOKED,
        UNKNOWN,
        NETWORK_UNAVAILABLE_AFTER_FALLBACK,
        RESPONDER_TRY_LATER_AFTER_FALLBACK,
        INVALID_RESPONSE
    }

    enum Policy {
        HARD_FAIL,
        SOFT_FAIL
    }

    enum Decision {
        ACCEPT,
        ACCEPT_WITH_WARNING,
        REJECT
    }

    static Decision decide(Status status, Policy policy) {
        switch (status) {
            case GOOD:
                return Decision.ACCEPT;
            case NETWORK_UNAVAILABLE_AFTER_FALLBACK:
            case RESPONDER_TRY_LATER_AFTER_FALLBACK:
                return policy == Policy.SOFT_FAIL
                        ? Decision.ACCEPT_WITH_WARNING : Decision.REJECT;
            case REVOKED:
            case UNKNOWN:
            case INVALID_RESPONSE:
            default:
                return Decision.REJECT;
        }
    }

    public static void main(String[] args) throws Exception {
        CertPathValidator validator =
                CertPathValidator.getInstance("PKIX");
        PKIXRevocationChecker checker =
                (PKIXRevocationChecker) validator.getRevocationChecker();
        checker.setOptions(EnumSet.of(
                PKIXRevocationChecker.Option.SOFT_FAIL));

        System.out.println("PKIX validator available = "
                + "PKIX".equals(validator.getAlgorithm()));
        System.out.println("SOFT_FAIL configured = "
                + checker.getOptions().contains(
                        PKIXRevocationChecker.Option.SOFT_FAIL));
        System.out.println("soft-fail exceptions before validation = "
                + checker.getSoftFailExceptions().size());

        System.out.println("good + hard-fail = "
                + decide(Status.GOOD, Policy.HARD_FAIL));
        System.out.println("revoked + soft-fail = "
                + decide(Status.REVOKED, Policy.SOFT_FAIL));
        System.out.println("network unavailable + hard-fail = "
                + decide(Status.NETWORK_UNAVAILABLE_AFTER_FALLBACK,
                        Policy.HARD_FAIL));
        System.out.println("network unavailable + soft-fail = "
                + decide(Status.NETWORK_UNAVAILABLE_AFTER_FALLBACK,
                        Policy.SOFT_FAIL));
        System.out.println("tryLater + soft-fail = "
                + decide(Status.RESPONDER_TRY_LATER_AFTER_FALLBACK,
                        Policy.SOFT_FAIL));
        System.out.println("unknown + soft-fail = "
                + decide(Status.UNKNOWN, Policy.SOFT_FAIL));
        System.out.println("invalid response + soft-fail = "
                + decide(Status.INVALID_RESPONSE, Policy.SOFT_FAIL));
    }
}
~~~

Biên dịch và chạy trên JDK có hỗ trợ target Java 8:

~~~bash
javac --release 8 RevocationPolicyDemo.java
java RevocationPolicyDemo
~~~

Trên JDK 8 trực tiếp, dùng `javac RevocationPolicyDemo.java`. Source chỉ dùng API Java 8.

**Stdout thực tế đã biên dịch và chạy xác minh:**

~~~text
PKIX validator available = true
SOFT_FAIL configured = true
soft-fail exceptions before validation = 0
good + hard-fail = ACCEPT
revoked + soft-fail = REJECT
network unavailable + hard-fail = REJECT
network unavailable + soft-fail = ACCEPT_WITH_WARNING
tryLater + soft-fail = ACCEPT_WITH_WARNING
unknown + soft-fail = REJECT
invalid response + soft-fail = REJECT
~~~

### 15.1. Vì sao revoked + soft-fail vẫn REJECT?

SOFT_FAIL chỉ liên quan những lỗi lấy status tạm thời được Java API cho phép bỏ qua. Một status REVOKED hợp lệ không thuộc nhóm đó; ứng dụng phải từ chối certificate.

### 15.2. Vì sao network unavailable chỉ ACCEPT_WITH_WARNING trong một policy?

Đây là quyết định của hàm nghiệp vụ mô phỏng sau khi nguồn ưu tiên và fallback đã thất bại vì lỗi được cho phép. Nếu policy là HARD_FAIL, cùng tình huống sẽ REJECT.

### 15.3. Vì sao UNKNOWN vẫn REJECT?

UNKNOWN có nghĩa responder đã trả lời nhưng không xác định được status. Nó không phải bằng chứng GOOD và không tự thuộc nhóm network errors mà Java SOFT_FAIL bỏ qua. Có thể thử nguồn khác; nếu vẫn unresolved, policy phải quyết định rõ, không biến UNKNOWN thành GOOD.

### 15.4. Vì sao invalid response không soft-fail?

Một response sai chữ ký, sai certificate identifier hoặc stale không phải bằng chứng đáng tin. Cho phép tiếp tục chỉ vì parser/network đã nhận được bytes sẽ làm giảm mức bảo vệ. Có thể thử nguồn tin cậy khác theo policy, nhưng không được xem response sai là GOOD.

### 15.5. Giới hạn của demo

- Không tạo certificate CA/test leaf.
- Không chạy PKIX validation trên chain thật.
- Không mở kết nối OCSP hoặc tải CRL.
- Không chứng minh provider fallback/timeout trên mọi JDK.
- Không phải benchmark.
- Không thay thế integration tests với test CA và responder có thể điều khiển.

Nó chỉ xác minh API Java 8 và logic quyết định minh họa. Hành vi mạng thực tế phải được kiểm thử trên đúng JDK/provider/deployment.

## 16. Những lỗi phổ biến và cách khắc phục

### Lỗi 1 — Không truy cập được OCSP nghĩa là certificate hợp lệ

Không có response không phải GOOD. **Sửa:** phân loại NETWORK_UNAVAILABLE và áp hard-fail/soft-fail đã phê duyệt.

### Lỗi 2 — Không truy cập được OCSP nghĩa là certificate đã bị thu hồi

Mất mạng không chứng minh trạng thái REVOKED. **Sửa:** tách trạng thái certificate khỏi kết quả truy xuất.

### Lỗi 3 — Dùng boolean cho mọi trạng thái

Không phân biệt UNKNOWN, INVALID và UNAVAILABLE. **Sửa:** dùng result enum/domain type có nguyên nhân.

### Lỗi 4 — Bật SOFT_FAIL rồi chấp nhận mọi exception

SOFT_FAIL chỉ bao phủ điều kiện được API quy định. **Sửa:** không nuốt CertPathValidatorException tổng quát; phân loại đúng lỗi.

### Lỗi 5 — SOFT_FAIL cho phép certificate revoked đi qua

Sai. Revoked không phải lỗi mạng. **Sửa:** giữ nguyên REJECT cho status revoked.

### Lỗi 6 — Coi OCSP UNKNOWN là GOOD

UNKNOWN nghĩa responder không xác định được. **Sửa:** thử nguồn khác hoặc từ chối theo policy nếu unresolved.

### Lỗi 7 — Coi response sai chữ ký là lỗi kết nối

Response không xác minh được là dữ liệu không đáng tin. **Sửa:** reject hoặc dùng nguồn tin cậy khác, không soft-fail.

### Lỗi 8 — Không kiểm tra freshness

Một response GOOD cũ có thể không còn đại diện status hiện tại. **Sửa:** kiểm tra thisUpdate/nextUpdate và policy staleness.

### Lỗi 9 — Dùng CRL hết hạn

Serial không có trong CRL stale không chứng minh certificate chưa bị thu hồi. **Sửa:** tải CRL mới hoặc áp unresolved policy.

### Lỗi 10 — Dùng serial number đơn lẻ làm cache key

Serial chỉ có nghĩa trong ngữ cảnh issuer. **Sửa:** kết hợp certificate/issuer identity.

### Lỗi 11 — Fallback khi nguồn đầu tiên đã trả REVOKED

Không được dùng một nguồn khác để hạ kết quả revoked hợp lệ. **Sửa:** xử lý conflict bảo thủ và điều tra.

### Lỗi 12 — Tắt fallback mà không hiểu hệ quả

Nguồn ưu tiên lỗi sẽ không có nguồn thứ hai. **Sửa:** chỉ đặt NO_FALLBACK theo yêu cầu policy và test.

### Lỗi 13 — Bật ONLY_END_ENTITY mà bỏ qua intermediate

Intermediate CA cũng có thể bị thu hồi. **Sửa:** chỉ dùng nếu scope policy cho phép rõ ràng.

### Lỗi 14 — Cấu hình checker sau khi add vào PKIXParameters

Parameters clone checker khi add; sửa object gốc sau đó không thay đổi bản đã thêm. **Sửa:** cấu hình đầy đủ trước add.

### Lỗi 15 — Chia sẻ một checker giữa nhiều threads

PKIXRevocationChecker không thread-safe. **Sửa:** tạo instance theo validation context hoặc đồng bộ đúng.

### Lỗi 16 — Tưởng setRevocationEnabled(false) vô hiệu custom checker đã gắn

Custom checker được dùng bất kể cờ RevocationEnabled. **Sửa:** hiểu khác biệt giữa default mechanism và explicit checker.

### Lỗi 17 — Tưởng ocsp.enable=true tự bật toàn bộ revocation

OCSP setting chỉ có tác dụng khi revocation checking cũng được bật và đúng provider path. **Sửa:** xác minh cả hai cấu hình.

### Lỗi 18 — Trộn explicit checker với provider default mà không test

Có thể tạo hành vi khó dự đoán hoặc cấu hình không như mong muốn. **Sửa:** xác định một đường validation rõ, đọc provider docs và integration test.

### Lỗi 19 — Không đặt read timeout

Responder có thể giữ kết nối lâu sau khi đã connect. **Sửa:** cấu hình connect và read timeout riêng nếu provider hỗ trợ.

### Lỗi 20 — Đặt timeout bằng zero để tránh lỗi

Trong Oracle JDK, zero có nghĩa timeout vô hạn. **Sửa:** chọn giới hạn hữu hạn theo SLA.

### Lỗi 21 — Retry vô hạn khi CA outage

Làm cạn thread và tạo tải thêm lên responder. **Sửa:** bounded retries, backoff/jitter và fallback.

### Lỗi 22 — Circuit breaker mở đồng nghĩa GOOD

Circuit breaker chỉ phản ánh trạng thái kết nối. **Sửa:** vẫn áp status policy cho UNAVAILABLE.

### Lỗi 23 — Cache GOOD không giới hạn

Certificate có thể bị thu hồi sau response đã cache. **Sửa:** tuân thủ freshness và nextUpdate.

### Lỗi 24 — Không giám sát soft-fail

Hệ thống có thể chấp nhận certificate mà người vận hành không biết. **Sửa:** metric, log có giới hạn và alert cho mọi soft-fail.

### Lỗi 25 — Bỏ qua kiểm tra certificate path khi status GOOD

Revocation GOOD không bảo đảm hostname, chain, expiry hay algorithm hợp lệ. **Sửa:** thực hiện đầy đủ PKIX/TLS validation.

### Lỗi 26 — Dùng trust-all TrustManager để giải quyết outage

Bỏ luôn trust validation. **Sửa:** giữ trust manager đúng và xử lý revocation policy ở đúng tầng.

### Lỗi 27 — Dùng CRL/OCSP status để thay thế hostname verification

Certificate chưa bị thu hồi vẫn có thể thuộc hostname khác. **Sửa:** kiểm tra endpoint identity riêng.

### Lỗi 28 — Không kiểm tra clock drift

Clock sai có thể làm response fresh bị coi là stale hoặc ngược lại. **Sửa:** đồng bộ thời gian và test clock skew.

### Lỗi 29 — Chỉ test OCSP thành công

Không bao phủ các outage/unknown/invalid/stale scenarios. **Sửa:** test từng kết quả và fallback.

### Lỗi 30 — Không phân biệt JDK update level

Một số tính năng TLS/OCSP phụ thuộc JDK update. **Sửa:** ghi nhận runtime version và kiểm tra chính xác bản triển khai.

## 17. Checklist thiết kế chính sách production

| Câu hỏi | Điều cần xác định |
| --- | --- |
| Certificate path được validate bằng provider nào? | PKIX implementation thực tế |
| Revocation checking có bật không? | Cờ và đường config đang được dùng |
| Dùng explicit PKIXRevocationChecker hay default provider? | Tránh trộn hành vi |
| OCSP hay CRL được ưu tiên? | PREFER_CRLS/default provider |
| Có fallback không? | NO_FALLBACK và policy |
| Soft-fail được phép cho lỗi nào? | Chỉ điều kiện cụ thể đã phê duyệt |
| REVOKED có luôn reject? | Quy tắc bất biến |
| UNKNOWN được xử lý ra sao? | Thử nguồn khác hoặc reject |
| INVALID response có bị từ chối? | Chữ ký/identity/freshness |
| CRL/OCSP response có fresh? | thisUpdate/nextUpdate |
| Có timeout connect và read? | SLA hữu hạn |
| Có bounded retry và backoff? | Tránh retry storm |
| Cache key có issuer identity? | Không dùng serial đơn lẻ |
| Cache GOOD có TTL/freshness? | Không giữ vô hạn |
| Có alert soft-fail? | Availability không che security |
| Có log provider/endpoint/status? | Debug và audit |
| Checker có được share giữa threads? | Không dùng instance mutable chung |
| Có xác minh TLS hostname riêng? | Không thay bằng revocation |
| Có test outage thật? | DNS/connect/read/proxy |
| Có test invalid/stale response? | Không soft-fail sai |
| Có test certificate revoked? | Luôn reject |
| Có test intermediate CA? | Scope toàn chain |
| Có kiểm thử JDK update/runtime? | Behavior provider-specific |
| Có người sở hữu quyết định fail-open? | Risk acceptance rõ ràng |

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Không truy cập được OCSP có chứng minh certificate chưa bị thu hồi không?

**Đáp án:** Không. Đây là NETWORK_UNAVAILABLE, không phải GOOD.

**Câu 2.** CRL là gì?

**Đáp án:** Danh sách certificate bị thu hồi do CA/CRL issuer phát hành và ký số, có thông tin thời gian và phạm vi.

**Câu 3.** OCSP có những trạng thái chính nào?

**Đáp án:** GOOD, REVOKED và UNKNOWN.

**Câu 4.** UNKNOWN có đồng nghĩa network timeout không?

**Đáp án:** Không. UNKNOWN là responder trả lời nhưng không xác định được status; timeout là lỗi truy xuất.

**Câu 5.** GOOD có thay thế toàn bộ PKIX validation không?

**Đáp án:** Không. Vẫn phải kiểm tra trust chain, chữ ký, thời hạn, hostname, usage và các policy khác.

**Câu 6.** Hard-fail nghĩa là gì?

**Đáp án:** Nếu không thể xác định revocation status theo policy, từ chối certificate.

**Câu 7.** Soft-fail nghĩa là gì?

**Đáp án:** Cho phép check thành công trong một số lỗi truy cập status được quy định, không phải bỏ qua mọi lỗi certificate.

**Câu 8.** Java SOFT_FAIL có bỏ qua REVOKED không?

**Đáp án:** Không. REVOKED vẫn phải bị từ chối.

**Câu 9.** Java SOFT_FAIL bao phủ những lỗi nào?

**Đáp án:** Các lỗi mạng khi lấy CRL/OCSP và một số OCSP responder errors như internalError/tryLater theo API contract.

**Câu 10.** Khi fallback còn bật, SOFT_FAIL có thể pass sau khi chỉ OCSP lỗi không?

**Đáp án:** Không theo hợp đồng Option: check chỉ được phép thành công khi cả OCSP và CRL đều thất bại vì điều kiện được cho phép.

**Câu 11.** `PREFER_CRLS` làm gì?

**Đáp án:** Đổi thứ tự ưu tiên sang CRL trong PKIXRevocationChecker.

**Câu 12.** `NO_FALLBACK` làm gì?

**Đáp án:** Tắt cơ chế fallback giữa các nguồn revocation.

**Câu 13.** `ONLY_END_ENTITY` có rủi ro gì?

**Đáp án:** Nó không kiểm tra revocation của intermediate CA; chỉ dùng khi policy cho phép.

**Câu 14.** Vì sao cấu hình checker trước khi add vào PKIXParameters?

**Đáp án:** Vì checker được clone khi thêm; thay đổi object gốc sau đó không thay đổi checker đã thêm.

**Câu 15.** Có nên share PKIXRevocationChecker mutable giữa threads?

**Đáp án:** Không. API không đảm bảo thread safety.

**Câu 16.** `setRevocationEnabled(false)` có vô hiệu custom checker đã add không?

**Đáp án:** Không. Checker tường minh được dùng bất kể cờ RevocationEnabled.

**Câu 17.** Vì sao response stale không được coi GOOD?

**Đáp án:** Dữ liệu không còn chứng minh trạng thái tại thời điểm hiện tại theo freshness policy.

**Câu 18.** Vì sao cache key cần issuer?

**Đáp án:** Serial number chỉ có ý nghĩa trong ngữ cảnh issuer; issuer khác nhau có thể có cùng serial.

**Câu 19.** Vì sao timeout zero nguy hiểm trong Oracle JDK properties?

**Đáp án:** Nó biểu thị không giới hạn thời gian, có thể giữ tài nguyên vô hạn khi responder treo.

**Câu 20.** OCSP stapling có làm client bỏ kiểm tra chữ ký response không?

**Đáp án:** Không. Client vẫn phải xác minh response và freshness.

**Câu 21.** Java 8 nào có client-driven OCSP cho TLS theo tài liệu Oracle?

**Đáp án:** JDK 8u261 trở lên; không suy ra mọi update Java 8 đều có cùng tính năng.

**Câu 22.** Khi nào UNKNOWN nên được chấp nhận?

**Đáp án:** Không tự động. Có thể thử nguồn khác; nếu unresolved, quyết định theo policy rủi ro, không coi UNKNOWN là GOOD.

**Câu 23.** Nếu một nguồn hợp lệ báo REVOKED nhưng nguồn khác không truy cập được thì sao?

**Đáp án:** Từ chối certificate và điều tra; không dùng lỗi truy cập để bỏ qua bằng chứng revoked.

**Câu 24.** Demo Java ở mục 15 có thực sự gửi OCSP request không?

**Đáp án:** Không. Nó xác minh API checker và mô phỏng policy decision; cần integration test riêng với test CA/responder.

## 19. Tổng kết

- **Không truy cập được nguồn kiểm tra thu hồi không đồng nghĩa certificate GOOD hoặc REVOKED.** Đó là một lỗi truy xuất status và phải được phân loại riêng.
- **CRL** là danh sách certificate revoked có chữ ký và freshness; **OCSP** trả status theo certificate với các trạng thái GOOD/REVOKED/UNKNOWN.
- **UNKNOWN, INVALID_RESPONSE, STALE_DATA và NETWORK_UNAVAILABLE khác nhau.** Không gộp tất cả thành “lỗi mạng” để soft-fail.
- **Hard-fail** từ chối khi không thể xác định status; **soft-fail** chỉ cho phép một số lỗi truy cập tạm thời theo policy và Java API.
- **Java 8 `PKIXRevocationChecker`** cung cấp `SOFT_FAIL`, `PREFER_CRLS`, `NO_FALLBACK` và `ONLY_END_ENTITY`. SOFT_FAIL không bỏ qua revoked hoặc các lỗi PKIX khác.
- Khi fallback bật, Java API quy định SOFT_FAIL chỉ có thể pass sau khi cả OCSP và CRL đều thất bại vì điều kiện được phép.
- **Timeout, retry, freshness, cache, clock và telemetry** là một phần của chính sách vận hành, không phải phần phụ của code.
- **Không dùng trust-all** hoặc catch-all exception để xử lý OCSP outage; giữ nguyên certificate chain validation và hostname verification.
- **Oracle provider defaults khác với explicit PKIXRevocationChecker**; xác minh JDK/provider và configuration đang chạy.
- **Chương trình Java 8 đã biên dịch và chạy** để xác minh checker API và mô phỏng hard/soft-fail decision. Integration test với CA/OCSP/CRL thật vẫn cần được thực hiện trong hệ thống triển khai.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — PKIXRevocationChecker.Option](https://docs.oracle.com/javase/8/docs/api/java/security/cert/PKIXRevocationChecker.Option.html)
- [Oracle Java SE 8 — PKIXRevocationChecker](https://docs.oracle.com/javase/8/docs/api/java/security/cert/PKIXRevocationChecker.html)
- [Oracle Java SE 8 — PKIXParameters](https://docs.oracle.com/javase/8/docs/api/java/security/cert/PKIXParameters.html)
- [Oracle Java SE 8 — PKI Programmer's Guide](https://docs.oracle.com/javase/8/docs/technotes/guides/security/certpath/CertPathProgGuide.html)
- [Oracle JDK 26 — PKIXRevocationChecker](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/PKIXRevocationChecker.html)
- [Oracle JDK 26 — Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/26/security/java-pki-programmers-guide.html)
- [Oracle Java 8u261+ — Client-Driven OCSP and OCSP Stapling](https://docs.oracle.com/javase/8/docs/technotes/guides/security/jsse/ocsp.html)
- [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280.html)
- [RFC 6960 — X.509 Online Certificate Status Protocol](https://www.rfc-editor.org/rfc/rfc6960.html)
- [RFC 5019 — Lightweight OCSP Profile for High-Volume Environments](https://www.rfc-editor.org/rfc/rfc5019.html)
