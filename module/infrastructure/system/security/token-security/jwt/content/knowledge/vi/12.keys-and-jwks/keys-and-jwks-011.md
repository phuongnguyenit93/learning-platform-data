# Xử lý mất kết nối nguồn khóa và tránh chấp nhận token khi không đủ bằng chứng

## 1. Vì sao mất kết nối nguồn khóa là một tình huống bảo mật?

JWT có thể được xác minh bằng khóa lấy từ cấu hình cục bộ, kho khóa, HSM/KMS hoặc một nguồn khóa từ xa như JSON Web Key Set (JWKS). Với mô hình JWKS, bên xác minh thường cần truy cập endpoint của issuer để nhận public key mới, cập nhật khóa đã xoay vòng hoặc xác nhận một khóa còn được công bố.

Nguồn khóa có thể tạm thời không truy cập được do:

- DNS, định tuyến, proxy hoặc kết nối mạng gặp lỗi.
- JWKS endpoint timeout, trả về lỗi máy chủ hoặc bị quá tải.
- TLS handshake thất bại hoặc chứng thư máy chủ không còn hợp lệ.
- Hệ thống quản lý khóa, HSM hoặc KMS không sẵn sàng.
- Response JWKS sai định dạng, vượt giới hạn hoặc không đáp ứng chính sách.
- Issuer đang xoay vòng khóa hoặc thay đổi cấu hình phân phối khóa.

Đây vừa là vấn đề khả dụng (availability), vừa là vấn đề xác thực (authentication). Khi không lấy được khóa, hệ thống có thể không đủ bằng chứng để xác minh chữ ký hoặc giải mã token. Việc bỏ qua bước xác minh để duy trì dịch vụ sẽ biến lỗi khả dụng thành lỗ hổng xác thực.

Nguyên tắc:

> Khi nguồn khóa không sẵn sàng, chỉ tiếp tục nếu có một khóa đã được tin cậy trước đó và chính sách cho phép sử dụng nó trong khoảng thời gian hiện tại. Nếu không đủ bằng chứng mật mã, phải từ chối token hoặc dừng thao tác.

Bài này tập trung vào bảo mật JWT/JOSE tổng quát, không phụ thuộc Java, Spring Security hay nền tảng triển khai.

## 2. Phân biệt lỗi khả dụng và lỗi tin cậy

Không phải mọi lỗi khi lấy khóa đều có thể xử lý bằng cùng một cơ chế dự phòng. Cần phân biệt lỗi tạm thời của hạ tầng với tín hiệu cho thấy nguồn dữ liệu hoặc cấu hình không còn đáng tin.

| Tình huống | Phân loại | Hướng xử lý |
| --- | --- | --- |
| Timeout kết nối tới JWKS endpoint đã cấu hình | Có thể là lỗi khả dụng tạm thời | Có thể dùng cache đã xác thực nếu còn trong giới hạn freshness/grace của policy |
| DNS tạm thời không phân giải được host đã cấu hình | Có thể là lỗi khả dụng | Áp dụng retry có giới hạn; chỉ dùng cache tin cậy trong thời gian được phép |
| JWKS endpoint trả HTTP 5xx | Thường là lỗi dịch vụ tạm thời | Dùng cache đã xác thực nếu policy cho phép; ghi nhận lỗi |
| JWKS endpoint trả 401/403 | Lỗi cấu hình hoặc quyền truy cập | Không tự động coi như outage thông thường; kiểm tra cấu hình/credential và áp dụng chính sách nghiêm ngặt |
| JWKS endpoint trả 404 | URI có thể sai hoặc tài nguyên đã bị gỡ | Không tự chuyển sang nguồn khác; từ chối nếu không có khóa cache còn được phép |
| TLS certificate hết hạn, hostname mismatch hoặc chain không hợp lệ | Lỗi xác thực nguồn | Không bỏ qua TLS; từ chối lần tải mới và cảnh báo |
| Redirect sang host không được phép | Vi phạm chính sách nguồn | Từ chối; không theo redirect ngoài allowlist |
| JWKS JSON sai định dạng hoặc có tham số khóa không hợp lệ | Dữ liệu nguồn không đáp ứng chính sách | Không nạp vào cache; không dùng khóa mới từ response |
| Khóa không phù hợp với alg/kty/use/key_ops | Lỗi chính sách khóa | Từ chối token; không thử khóa hoặc thuật toán khác |
| KMS/HSM không thực hiện được thao tác mật mã | Nguồn khóa hoặc dịch vụ mật mã không sẵn sàng | Dừng thao tác cần khóa đó; không bỏ qua kiểm tra |

Một lỗi TLS hoặc response không hợp lệ không nên bị che giấu bằng cách âm thầm chấp nhận mọi dữ liệu cache cũ vô thời hạn. Nếu có cơ chế dùng last-known-good (LKG), phải giới hạn rõ trường hợp được dùng và thời gian tối đa.

## 3. Cache JWKS và khóa đã xác thực trước đó

Cache có thể giúp hệ thống tiếp tục xác minh token trong một outage ngắn. Điều kiện là cache chứa khóa được lấy từ nguồn tin cậy, đã được kiểm tra đầy đủ và vẫn còn được policy cho phép sử dụng.

Một snapshot JWKS chỉ nên được đưa vào cache sau khi:

1. Response đến từ JWKS URI đã cấu hình cho đúng issuer.
2. Kết nối và danh tính máy chủ được xác minh theo chính sách TLS.
3. Response nằm trong giới hạn kích thước, thời gian và số lượng khóa.
4. JSON được parse nghiêm ngặt và cấu trúc JWK Set hợp lệ.
5. Mỗi khóa được kiểm tra tham số, loại khóa, thuật toán, mục đích và thao tác.
6. Tập khóa phù hợp với chính sách issuer/profile.

Không ghi đè cache tốt bằng response một phần, response sai định dạng hoặc response đến từ nguồn không được xác minh. Nên thay thế snapshot theo cách nguyên tử: hoặc toàn bộ snapshot mới được chấp nhận, hoặc giữ snapshot cũ theo chính sách.

### Metadata nên lưu cùng cache

| Metadata | Mục đích |
| --- | --- |
| Issuer và JWKS URI đã cấu hình | Giữ ranh giới nguồn tin cậy |
| Thời điểm fetch thành công | Tính tuổi cache và freshness |
| Thời điểm hết hạn/freshness deadline | Xác định khi nào cần refresh hoặc từ chối |
| Thời điểm refresh gần nhất và lỗi gần nhất | Theo dõi outage và điều phối retry |
| ETag/Last-Modified nếu nguồn hỗ trợ | Hỗ trợ conditional request |
| Danh sách kid và metadata khóa đã xác thực | Tra cứu khóa theo ngữ cảnh |
| Phiên bản hoặc fingerprint snapshot | Phát hiện thay đổi và hỗ trợ điều tra |
| Trạng thái/ghi chú thu hồi hoặc denylist cục bộ | Ngăn tiếp tục dùng khóa đã bị vô hiệu hóa |

Cache key phải gắn với issuer, nguồn JWKS và ngữ cảnh sử dụng. Không cache khóa chỉ theo chuỗi `kid` trên toàn hệ thống vì nhiều issuer có thể dùng cùng một giá trị `kid`.

## 4. Fresh cache, stale cache và giới hạn dùng khóa cũ

Khi JWKS endpoint mất kết nối, quyết định dùng cache phụ thuộc vào tuổi cache và policy của ứng dụng.

### Cache còn fresh

Nếu khóa đã được lấy từ nguồn tin cậy, cache vẫn trong khoảng freshness được cấu hình và không có tín hiệu thu hồi/khóa bị vô hiệu hóa, hệ thống có thể tiếp tục xác minh chữ ký bằng khóa đã cache. Việc fetch JWKS thất bại không làm mất giá trị của một public key đã được xác thực trước đó.

Điều kiện:

- Token khai báo `kid` khớp đúng một khóa trong snapshot.
- Thuật toán nằm trong allowlist và khớp ràng buộc của khóa.
- Khóa vẫn được policy cho phép sử dụng.
- Chữ ký được xác minh thành công.
- Claims vẫn phải qua kiểm tra issuer, audience, thời hạn và profile.

### Cache stale nhưng còn trong grace period

Một hệ thống có thể định nghĩa khoảng thời gian grace ngắn để dùng last-known-good JWKS khi gặp lỗi khả dụng tạm thời. Đây là **quyết định policy theo rủi ro**, không phải quyền mặc định để dùng cache cũ vô thời hạn.

Khi cho phép stale fallback, cần:

1. Chỉ dùng snapshot trước đó đã xác thực đầy đủ.
2. Đặt giới hạn tuổi tối đa tuyệt đối (maximum stale age).
3. Chỉ kích hoạt với các lỗi khả dụng được policy liệt kê, chẳng hạn timeout hoặc 5xx.
4. Không dùng stale fallback để vượt qua lỗi xác minh TLS, nguồn sai host, response giả mạo hoặc cấu hình tin cậy bị thay đổi.
5. Không chấp nhận khóa đã có chỉ thị thu hồi/denylist hoặc bị vô hiệu hóa khẩn cấp.
6. Phát cảnh báo và tiếp tục thử refresh theo lịch có giới hạn.
7. Khi vượt grace period, từ chối token cần nguồn khóa đó cho tới khi khôi phục được bằng chứng tin cậy.

### Cache đã quá giới hạn

Nếu snapshot cũ vượt maximum stale age, hệ thống không còn đủ căn cứ để khẳng định khóa vẫn được phép. Khi đó phải từ chối xác minh phụ thuộc vào snapshot đó. Không kéo dài freshness mỗi khi một lần refresh thất bại; làm vậy sẽ khiến cache có thể tồn tại vô hạn trong outage kéo dài.

### Bảng quyết định

| Trạng thái nguồn khóa | Khóa có trong cache? | Hành vi |
| --- | --- | --- |
| JWKS tải và xác thực thành công | Có, khóa hợp lệ | Dùng snapshot mới sau khi kiểm tra đầy đủ |
| JWKS tạm thời không truy cập được | Có, cache còn fresh | Có thể xác minh bằng khóa cache |
| JWKS tạm thời không truy cập được | Có, cache stale nhưng còn grace được policy cho phép | Có thể tiếp tục có điều kiện, ghi cảnh báo và giới hạn thời gian |
| JWKS tạm thời không truy cập được | Có, cache quá maximum stale age | Từ chối |
| JWKS tạm thời không truy cập được | Không có khóa phù hợp | Từ chối |
| JWKS trả dữ liệu không hợp lệ | Có cache LKG | Không dùng response mới; chỉ xem xét LKG nếu chính sách lỗi và freshness cho phép |
| TLS/source validation thất bại | Có cache LKG | Không bỏ qua lỗi xác thực nguồn; chỉ dùng cache nếu policy có quy định rõ cho tình huống này, nếu không thì từ chối |
| Khóa bị thu hồi/vô hiệu hóa khẩn cấp | Có cache cũ | Từ chối khóa đó và vô hiệu hóa cache liên quan |

Không có một con số freshness/grace phù hợp cho mọi hệ thống. Token có quyền cao, dữ liệu nhạy cảm hoặc môi trường có yêu cầu thu hồi nhanh cần giới hạn ngắn hơn hoặc không cho stale fallback. Một hệ thống chấp nhận stale cache phải ghi rõ trade-off: tăng khả dụng nhưng có thể chậm nhận biết khóa đã bị gỡ khỏi JWKS.

## 5. Điều gì xảy ra khi gặp `kid` chưa biết?

Đây là trường hợp cần xử lý nghiêm ngặt nhất khi nguồn JWKS không sẵn sàng.

Giả sử token có header:

~~~json
{
  "alg": "PS256",
  "kid": "issuer-signing-key-new"
}
~~~

Nhưng cache hiện tại không có `issuer-signing-key-new`. Có thể issuer vừa xoay vòng khóa và token được ký bằng khóa mới, hoặc token do kẻ tấn công tự tạo với `kid` ngẫu nhiên.

Quy trình an toàn:

1. Tìm `kid` trong snapshot cache của đúng issuer/profile.
2. Nếu không có, chỉ thực hiện một lần refresh có giới hạn tới JWKS URI đã cấu hình; gộp các request đồng thời nếu có.
3. Nếu refresh thành công, xác thực toàn bộ JWKS rồi tìm lại khóa.
4. Nếu `kid` vẫn không có hoặc refresh thất bại, từ chối token.
5. Không thử mọi khóa không liên quan, không dùng khóa từ issuer khác và không bỏ qua chữ ký.

**Không được dùng stale cache để xác minh một `kid` chưa từng được tin cậy.** Cache cũ chỉ có thể hỗ trợ khóa đã có trong snapshot trước đó; nó không tạo ra bằng chứng cho khóa mới.

### Vì sao không thử khóa bất kỳ?

Việc thử tất cả khóa trong cache hoặc kho khóa:

- Làm tăng chi phí CPU theo số lượng khóa và tạo điều kiện DoS.
- Có thể chọn nhầm khóa thuộc issuer/tenant hoặc mục đích khác.
- Làm mờ ranh giới giữa khóa đã được cấp phép và khóa chỉ tình cờ xác minh được.
- Tạo hành vi khác nhau giữa các implementation.

Chỉ cho phép thử một tập ứng viên nếu giao thức quy định rõ, tập đó được giới hạn và mọi khóa đều thuộc đúng issuer, thuật toán và mục đích. Với mô hình JWKS phổ biến, chọn đúng một khóa theo `kid` và policy là cách rõ ràng hơn.

## 6. Không bỏ qua xác minh khi nguồn khóa lỗi

Khi JWKS hoặc KMS không truy cập được, các cách xử lý sau đều không an toàn:

- Decode payload rồi chấp nhận claims vì không thể lấy public key.
- Chấp nhận chữ ký rỗng hoặc chuyển sang `alg=none`.
- Bỏ qua bước kiểm tra chữ ký nhưng vẫn tạo authenticated principal.
- Chuyển sang thuật toán khác hoặc dùng một khóa mặc định không gắn với issuer.
- Lấy khóa từ `jwk`, `jku`, `x5u` do token tự khai mà không có trust anchor.
- Dùng khóa của issuer khác vì cùng có `kid` hoặc cùng loại thuật toán.
- Coi lỗi kết nối là bằng chứng token hợp lệ.

Mất kết nối chỉ nói rằng hệ thống chưa lấy được dữ liệu mới. Nó không làm giảm yêu cầu xác minh mật mã. Nếu không có khóa hợp lệ và được tin cậy, kết quả phải là **không xác minh được**, không phải **đã xác minh**.

## 7. Xoay vòng khóa trong thời gian có outage

Rollover cần được thiết kế để bên xác minh có thể nhận khóa mới trước khi issuer bắt đầu ký token bằng khóa đó.

Quy trình bình thường:

1. Issuer công bố public key mới trong JWKS.
2. Bên xác minh tải và xác thực JWKS mới; cache snapshot chứa cả khóa cũ và khóa mới.
3. Issuer bắt đầu ký token bằng khóa mới và `kid` mới.
4. Bên xác minh dùng khóa mới để xác minh token; vẫn giữ khóa cũ trong thời gian token cũ còn hiệu lực.
5. Sau thời gian chuyển tiếp, issuer gỡ khóa cũ; bên xác minh cập nhật cache khi refresh thành công.

Nếu JWKS endpoint outage đúng lúc issuer bắt đầu dùng khóa mới:

- Token dùng khóa mới có `kid` chưa biết phải bị từ chối cho đến khi có thể lấy được khóa từ nguồn tin cậy.
- Token dùng khóa cũ vẫn có thể được xác minh bằng cache nếu khóa còn fresh hoặc nằm trong grace period được policy cho phép.
- Không được tự tạo hoặc suy đoán public key mới từ token.
- Issuer nên có quy trình rollover tránh phụ thuộc vào việc mọi consumer đều refresh đúng thời điểm; công bố khóa trước và có giai đoạn overlap.

~~~mermaid
flowchart TD
    A["Issuer công bố key-new trong JWKS"] --> B["Verifier refresh và xác thực snapshot"]
    B --> C["Issuer bắt đầu ký bằng kid-new"]
    C --> D{"JWKS endpoint có sẵn?"}
    D -- Có --> E["Verifier tải snapshot mới và chọn key-new"]
    D -- Không --> F{"kid-new đã có trong cache tin cậy?"}
    F -- Có --> G["Xác minh bằng key-new theo freshness policy"]
    F -- Không --> H["Từ chối token; chờ nguồn khóa khôi phục"]
    E --> I["Xác minh chữ ký và claims"]
    G --> I
~~~

Rollover không nên dựa vào việc giữ khóa cũ vô thời hạn. Khóa cũ có thể đã bị thu hồi hoặc bị lộ; thời gian overlap phải tương ứng với thời hạn token, clock skew và yêu cầu thu hồi của hệ thống.

## 8. Thu hồi khóa và tình huống khẩn cấp

Việc issuer gỡ một JWK khỏi JWKS có thể là cách báo hiệu khóa không còn được sử dụng, nhưng consumer chỉ biết thay đổi này sau khi nhận được snapshot mới. Nếu JWKS endpoint đang lỗi, cache cũ có thể tiếp tục chứa khóa đã bị gỡ.

Vì vậy, hệ thống cần phân biệt:

- **Rollover bình thường:** giữ khóa cũ trong giai đoạn overlap để xác minh token cũ.
- **Retirement:** khóa không còn được dùng để phát hành token mới nhưng vẫn có thể cần để xác minh token còn hiệu lực.
- **Emergency revocation/compromise:** khóa không còn được phép tin cậy; phải vô hiệu hóa ngay theo kênh điều phối khẩn cấp.

Đối với khóa bị xâm phạm:

1. Đưa `kid` hoặc fingerprint khóa vào denylist/trust policy cập nhật qua kênh quản trị tin cậy.
2. Xóa hoặc đánh dấu không sử dụng các cache entry liên quan.
3. Từ chối mọi token cần khóa bị vô hiệu hóa, kể cả token có chữ ký toán học hợp lệ.
4. Xoay khóa và cập nhật JWKS qua kênh đã xác thực.
5. Đánh giá token đã phát hành và quyết định thu hồi session/token theo chính sách.
6. Theo dõi consumer chưa nhận được cập nhật và hạn chế thời gian tiếp tục chấp nhận cache cũ.

Không thể dựa vào JWKS đang mất kết nối để biết một khóa vừa bị thu hồi. Với hệ thống cần thu hồi nhanh, cần kênh phân phối trạng thái khẩn cấp độc lập hoặc chính sách freshness rất ngắn. Nếu không có cơ chế như vậy, phải thừa nhận rằng stale fallback làm tăng cửa sổ rủi ro.

## 9. Xử lý outage với các loại nguồn khóa khác nhau

### JWKS từ xa dùng public key để xác minh JWS

- Cache public key đã xác thực có thể tiếp tục dùng trong giới hạn freshness/grace.
- `kid` mới chưa có trong cache phải bị từ chối nếu không lấy được JWKS mới.
- Không bỏ qua chữ ký hoặc dùng khóa do token tự cung cấp.

### KMS/HSM giữ private key để ký

Nếu issuer cần KMS/HSM để ký token nhưng dịch vụ đó không sẵn sàng:

- Dừng phát hành token cần khóa đó cho đến khi thao tác ký thực hiện được.
- Không phát hành Unsecured JWT hoặc chuyển sang khóa mặc định yếu hơn.
- Không xuất private key ra file hoặc bộ nhớ tạm chỉ để né outage.
- Nếu có một khóa ký dự phòng, chỉ dùng khi nó đã được cấp phép, phân phối public key tương ứng và được bên nhận tin cậy trước.

### KMS/HSM giữ private key để giải mã JWE

Nếu recipient không thể truy cập private key cần thiết:

- Không thể hoàn tất giải mã/xác thực JWE; từ chối thao tác.
- Không dùng public key hoặc khóa của recipient khác để thử giải mã nếu không có quy tắc recipient rõ ràng.
- Không trả plaintext một phần trước khi authentication tag được xác minh.
- Có thể dùng một bản sao/replica HSM đã được quản trị nếu policy cho phép và cùng bảo vệ vật liệu khóa.

### Khóa HMAC hoặc secret đối xứng

Với HS256/HS384/HS512, bên xác minh cần secret dùng chung. Nếu secret được lấy từ secret manager:

- Chỉ dùng bản cache secret đã được bảo vệ và còn trong thời gian policy cho phép.
- Không ghi secret vào log, file tạm hoặc cache không mã hóa.
- Không thay secret bằng một giá trị rỗng, giá trị mặc định hoặc secret khác khi nguồn lỗi.
- Không chấp nhận token chỉ vì không thể truy cập secret manager.

## 10. Kiến trúc cache và refresh an toàn

Một thiết kế vận hành tốt tách việc refresh nguồn khóa khỏi luồng xử lý request khi có thể:

- Background refresh trước khi cache hết hạn, có jitter để tránh nhiều consumer refresh cùng lúc.
- Request path tra cứu snapshot đã xác thực và không chờ mạng vô hạn.
- Khi `kid` chưa biết, có một lần refresh có giới hạn và single-flight theo issuer.
- Dùng exponential backoff với jitter cho lỗi khả dụng; không retry liên tục theo từng request.
- Dùng circuit breaker để bảo vệ JWKS endpoint và consumer; circuit breaker chỉ kiểm soát kết nối, không thay đổi kết quả xác minh token.
- Giữ last-known-good snapshot bất biến và thay thế nguyên tử khi snapshot mới được xác thực.
- Tách cache theo issuer/tenant/profile và mục đích sử dụng khóa.
- Có cơ chế denylist hoặc invalidate cache khi khóa bị thu hồi khẩn cấp.

### Mã giả xử lý JWKS outage

~~~text
function getTrustedKey(issuerPolicy, kid, algorithm):
    snapshot = cache.get(issuerPolicy.cacheIdentity)

    if snapshot.containsUsableKey(kid, algorithm):
        if snapshot.isFresh():
            return snapshot.getUniqueKey(kid, algorithm)

        if snapshot.isWithinMaximumStaleAge()
           and issuerPolicy.allowsStaleOnTransientOutage
           and not issuerPolicy.isKeyRevoked(kid):
            refreshResult = refreshConfiguredJwksWithSingleFlightAndTimeout()
            if refreshResult.isValid:
                return refreshResult.getUniqueKeyOrReject(kid, algorithm)
            if refreshResult.isTransientAvailabilityFailure:
                emitStaleCacheWarning(issuerPolicy, kid)
                return snapshot.getUniqueKey(kid, algorithm)
            reject("JWKS source or response failed security validation")

    else:
        refreshResult = refreshConfiguredJwksWithSingleFlightAndTimeout()
        if refreshResult.isValid:
            return refreshResult.getUniqueKeyOrReject(kid, algorithm)
        reject("No trusted key available for this kid")

    reject("Trusted key unavailable or stale beyond policy")
~~~

Mã giả chỉ minh họa nguyên tắc. Trong triển khai thực tế, nếu cache stale và refresh thành công nhưng khóa đã bị gỡ khỏi JWKS mới, phải tuân theo policy rollover/retirement/revocation; không tự giữ khóa cũ chỉ vì nó từng tồn tại. Nếu khóa có tín hiệu thu hồi hoặc denylist, từ chối ngay cả khi cache còn fresh.

## 11. Quan sát, cảnh báo và vận hành

Outage nguồn khóa cần được quan sát như một sự kiện bảo mật và vận hành. Nên ghi nhận:

- Issuer và JWKS URI theo định danh cấu hình (không ghi token).
- Thời điểm refresh thành công gần nhất.
- Tuổi snapshot cache và thời gian còn lại trước maximum stale age.
- Số lần timeout, lỗi DNS, TLS, HTTP status và lỗi parse/validation.
- Số token bị từ chối vì `kid` chưa biết hoặc không có khóa phù hợp.
- Số lần dùng stale cache và thời gian stale thực tế.
- Số lần circuit breaker mở/đóng.
- Các sự kiện key rotation, retirement và emergency revocation.

Không ghi raw JWT, private key, HMAC secret hoặc toàn bộ payload vào log. Nếu cần điều tra token, chỉ ghi fingerprint/ID an toàn theo chính sách và che thông tin định danh nhạy cảm.

Ngưỡng cảnh báo nên dựa trên:

- Không có lần refresh thành công trong một khoảng thời gian định trước.
- Cache gần chạm maximum stale age.
- Tỷ lệ `kid` không biết tăng bất thường.
- JWKS response thay đổi mạnh về số lượng hoặc metadata khóa.
- TLS validation failure hoặc nguồn JWKS thay đổi ngoài lịch.
- Khóa bị thu hồi nhưng consumer vẫn có request dùng khóa đó.

## 12. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Bỏ qua xác minh khi JWKS endpoint lỗi | Token giả có thể được chấp nhận | Không đủ khóa tin cậy thì từ chối |
| Dùng cache cũ vô thời hạn | Khóa đã bị thu hồi vẫn có thể được chấp nhận | Đặt freshness và maximum stale age |
| Gia hạn TTL mỗi khi refresh thất bại | Cache stale không có giới hạn | Giữ nguyên thời điểm fetch thành công; không reset tuổi cache |
| Dùng stale cache cho `kid` chưa từng thấy | Không có bằng chứng về khóa mới | Unknown kid phải refresh giới hạn rồi từ chối nếu vẫn không tìm thấy |
| Chấp nhận response JWKS sai TLS hoặc sai nguồn | Nguồn khóa giả có thể đầu độc cache | Không bỏ qua TLS/source validation |
| Ghi đè LKG bằng response một phần/sai định dạng | Mất snapshot tốt hoặc nạp khóa không hợp lệ | Validate toàn bộ rồi thay thế nguyên tử |
| Thử mọi khóa trong mọi issuer | Nhầm lẫn ranh giới tin cậy và tăng DoS | Phân vùng cache, chọn khóa theo issuer/kid/alg |
| Retry liên tục theo từng request | Tạo bão request tới JWKS endpoint | Backoff, jitter, single-flight và circuit breaker |
| Dùng khóa dự phòng không được đăng ký trước | Mở rộng trust ngoài kiểm soát | Chỉ dùng khóa dự phòng đã provision và được consumer tin cậy |
| Bỏ qua thu hồi vì cache còn fresh | Khóa bị compromise tiếp tục được dùng | Kênh emergency denylist/invalidation |
| Kéo dài thời hạn token để bù outage | Mở rộng thời gian credential có hiệu lực | Giữ nguyên exp và chính sách thời hạn token |
| Phát hành JWT không ký khi KMS ký lỗi | Mất tính toàn vẹn và xác thực nguồn | Dừng phát hành hoặc dùng khóa dự phòng đã được quản trị |
| Dùng public key recipient khác để giải mã JWE | Có thể nhầm recipient hoặc sai tenant | Chọn đúng recipient/key theo policy; nếu không có thì từ chối |

## 13. Bộ ca kiểm thử outage và fail-closed

Giả sử API xác minh access token JWS từ một issuer, dùng PS256 và JWKS URI đã cấu hình. Policy cho phép dùng last-known-good cache tối đa 10 phút chỉ với lỗi timeout/5xx tạm thời. Con số này là ví dụ cho test, không phải giá trị khuyến nghị chung.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| JWKS hoạt động, khóa mới hợp lệ, chữ ký và claims đúng | **Chấp nhận** |
| JWKS timeout, `kid` đã có trong cache fresh | **Chấp nhận** nếu chữ ký/claims hợp lệ |
| JWKS 5xx, `kid` đã có trong LKG cache stale 3 phút và policy cho phép | Có thể **chấp nhận** trong grace, đồng thời cảnh báo |
| JWKS timeout, LKG cache stale 11 phút vượt giới hạn 10 phút | **Từ chối** |
| JWKS timeout, `kid` chưa từng có trong cache | **Từ chối** sau refresh giới hạn |
| JWKS timeout, token khai `kid` của issuer khác | **Từ chối** |
| JWKS timeout, token có chữ ký rỗng hoặc `alg=none` | **Từ chối** |
| JWKS TLS hostname mismatch | **Từ chối** lần tải; không tắt TLS validation |
| JWKS trả JSON sai cấu trúc | Không nạp response; chỉ dùng LKG nếu đúng điều kiện policy, nếu không thì **từ chối** |
| JWKS mới hợp lệ nhưng đã gỡ khóa cũ | Áp dụng policy retirement/revocation; không tự giữ khóa cũ vô thời hạn |
| Khóa nằm trong emergency denylist dù cache còn fresh | **Từ chối** |
| JWKS refresh đồng thời do nhiều request `kid` lạ | Chỉ một refresh theo single-flight; các request khác chờ giới hạn hoặc bị từ chối |
| KMS không sẵn sàng khi cần ký JWT | Không phát hành token; không fallback sang none |
| KMS/HSM không sẵn sàng khi cần giải mã JWE | **Từ chối** thao tác; không trả plaintext một phần |
| HMAC secret manager lỗi, secret cache đã vượt giới hạn | **Từ chối**; không dùng secret mặc định |
| Circuit breaker đang mở, cache có khóa fresh và phù hợp | Vẫn có thể xác minh cục bộ theo policy; circuit breaker không làm mất hiệu lực khóa đã cache |

Kiểm thử cần xác nhận kết quả từ chối không tạo authenticated context, không cấp quyền và không cho phép xử lý nghiệp vụ tiếp tục. Với stale fallback, cần kiểm tra chính xác thời điểm fetch thành công, tuổi cache, loại lỗi và trạng thái thu hồi.

## 14. Ghi nhớ

- Mất kết nối nguồn khóa là lỗi khả dụng, không phải bằng chứng token hợp lệ.
- Có thể tiếp tục xác minh bằng khóa cache đã được tin cậy nếu cache còn fresh và policy cho phép.
- Stale fallback chỉ nên có giới hạn thời gian, loại lỗi và phạm vi issuer/khóa rõ ràng; không gia hạn cache vô hạn khi refresh thất bại.
- `kid` chưa từng được tin cậy phải được refresh từ nguồn đã cấu hình; nếu không tìm được khóa thì từ chối.
- Không bỏ qua chữ ký, không fallback sang `alg=none`, không dùng khóa của issuer khác và không lấy khóa tùy ý từ token.
- Response JWKS mới chỉ thay thế last-known-good sau khi TLS, cấu trúc, khóa và policy đều được xác thực.
- Cần cơ chế thu hồi khẩn cấp để vô hiệu hóa cache khi khóa bị compromise; stale cache có thể làm chậm nhận biết khóa đã bị gỡ.
- Với KMS/HSM hoặc secret manager, nếu không thể thực hiện thao tác mật mã bằng khóa được phép thì dừng thao tác; không dùng secret mặc định hoặc phát hành token không bảo vệ.
- Sau khi xác minh chữ ký thành công, vẫn phải kiểm tra issuer, audience, thời hạn, loại token và quyền theo profile.

### Tài liệu chuẩn tham khảo

- [RFC 7517 — JSON Web Key (JWK), mục 5](https://www.rfc-editor.org/rfc/rfc7517): cấu trúc JWK Set và phân phối tập khóa.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): xác minh chữ ký JWS và các tham số header liên quan đến khóa.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): xử lý khóa, recipient và xác thực nội dung JWE.
- [RFC 8725 — JSON Web Token Best Current Practices, mục 3.1](https://www.rfc-editor.org/rfc/rfc8725): yêu cầu xác minh thuật toán và ràng buộc với chính sách phía ứng dụng.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): xử lý lỗi HTTP, status code và request semantics.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): freshness, validation và việc sử dụng response cache.
