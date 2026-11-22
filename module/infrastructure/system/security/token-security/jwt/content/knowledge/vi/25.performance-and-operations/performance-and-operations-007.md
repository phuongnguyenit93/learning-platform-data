# Chỉ số lỗi chữ ký, hết hạn, sai audience và không tìm thấy khóa

## 1. Vì sao cần theo dõi riêng các nhóm lỗi xác minh JWT?

Một hệ thống xác minh JSON Web Token (JWT) cần quan sát được cả hai mặt: credential có hợp lệ theo chính sách bảo mật hay không, và dịch vụ có đủ khả năng thực hiện việc xác minh một cách ổn định hay không. Nếu chỉ đếm tổng số request bị từ chối, đội vận hành sẽ khó phân biệt một đợt token hết hạn do client cũ, một lỗi cấu hình audience, một lần rotate signing key chưa đồng bộ hay một cuộc dò tìm key ID bất thường.

Bốn nhóm tín hiệu thường có giá trị vận hành cao:

1. **Signature invalid:** chữ ký không xác minh được bằng khóa và thuật toán được tin cậy.
2. **Expired token:** thời điểm hiện tại đã vượt quá thời hạn của token theo clock policy.
3. **Invalid audience:** token không được phát hành cho resource server đang nhận request.
4. **Key not found:** không tìm được khóa phù hợp với issuer, key ID và token profile.

Các nhóm này có thể phản ánh lỗi client, thay đổi cấu hình, sự cố key distribution, token substitution hoặc hành vi tấn công. Không nhóm nào tự nó chứng minh một cuộc tấn công. Cần kết hợp tỷ lệ, xu hướng, nguồn phát sinh, kết quả JWKS refresh, trạng thái triển khai và các tín hiệu liên quan.

Ví dụ:

~~~text
Traffic JWT tăng bình thường
       |
       +--> Signature invalid tăng đột biến
       |       |
       |       +--> Kiểm tra key rotation, issuer, thuật toán,
       |            token tampering và cấu hình verifier
       |
       +--> Expired tăng dần
       |       |
       |       +--> Kiểm tra client giữ token cũ, TTL,
       |            clock skew và refresh flow
       |
       +--> Invalid audience tăng tại một API
       |       |
       |       +--> Kiểm tra resource/audience mapping,
       |            token exchange và routing
       |
       +--> Key not found tăng theo nhiều kid lạ
               |
               +--> Kiểm tra unknown-kid storm, JWKS cache,
                    issuer binding và refresh throttling
~~~

Mục tiêu của observability là giúp người vận hành xác định điều gì đang xảy ra, ảnh hưởng tới ai và cần kiểm tra ở đâu. Nó không được làm suy yếu validation để giảm số lỗi.

Nguyên tắc cốt lõi:

> **Đo lường phải phân biệt credential không hợp lệ với verifier hoặc dependency không hoạt động. Khi không đủ bằng chứng để xác minh token, hệ thống vẫn phải từ chối theo chính sách.**

Bài này thuộc phạm vi Security chung của JSON Web Token (JWT), OAuth 2.0 và OpenID Connect. Các metric, dashboard và runbook áp dụng cho mọi nền tảng xác minh token, không phụ thuộc ngôn ngữ lập trình hoặc framework cụ thể.

## 2. Phân biệt lỗi token và lỗi vận hành

Một request không được xác thực có thể bị từ chối vì token sai, hoặc vì hệ thống không thể hoàn thành một bước xác minh bắt buộc. Hai trường hợp có kết quả bảo mật giống nhau là không tạo quyền truy cập, nhưng ý nghĩa vận hành khác nhau.

| Nhóm kết quả | Ví dụ | Cách hiểu |
| --- | --- | --- |
| Credential invalid | Signature invalid, expired, wrong issuer, wrong audience, wrong token type | Request mang credential không đáp ứng token profile. |
| Key/trust evidence invalid | kid không có trong JWKS tin cậy, JWK sai loại, issuer không được cấu hình | Không có khóa hoặc trust record hợp lệ để xác minh. |
| Dependency unavailable | JWKS timeout, introspection lỗi, replay store không truy cập được | Không thể hoàn tất một kiểm tra bắt buộc. |
| Internal verifier failure | Crypto provider lỗi, parser exception không dự kiến, cấu hình thiếu | Lỗi trong thành phần xác minh hoặc cấu hình vận hành. |
| Authorization denied | Token hợp lệ nhưng thiếu scope hoặc không có quyền trên object | Authentication thành công, quyết định authorization từ chối. |

Không gộp mọi trường hợp vào một counter invalid_token. Ví dụ, JWKS endpoint timeout không chứng minh token của người dùng sai; nó cho biết verifier không lấy được bằng chứng khóa cần thiết. Nếu key đã được xác minh và cache vẫn nằm trong policy freshness/stale, verifier có thể tiếp tục xác minh offline. Nếu không có key đáng tin cậy, request phải bị từ chối và sự kiện phải được đo như lỗi key/trust dependency.

### 2.1. Phân biệt authentication và authorization

Một access token có thể xác minh thành công nhưng request vẫn bị từ chối vì:

- Scope không đủ.
- Subject không thuộc tenant.
- User không sở hữu resource.
- Action không được phép.
- Tài khoản hoặc membership đã bị khóa.

Các trường hợp này không phải signature failure, expired token hay audience mismatch. Cần metric riêng cho authorization denial để tránh hiểu sai chất lượng token issuer.

### 2.2. Phân biệt request thiếu token

Request không gửi Authorization credential là một trường hợp khác với request gửi JWT không hợp lệ. Nên có metric riêng như missing_credential hoặc unauthenticated_request nếu API cần theo dõi. Không đếm request thiếu token thành signature invalid.

## 3. Mô hình đo lường: attempt, outcome và reason

Trước khi đặt tên metric, cần xác định một đơn vị đo ổn định.

### 3.1. Một validation attempt là gì?

Một validation attempt là một lần hệ thống xử lý một credential tại một điểm xác minh, theo một token profile và endpoint cụ thể. Một request có thể tạo nhiều attempt nếu kiến trúc có Gateway và backend cùng xác minh token; vì vậy cần biết metric đang đếm tại verifier nào.

Nên xác định:

- Đếm một lần cho mỗi lần verifier bắt đầu xử lý token.
- Ghi nhận đúng một kết quả cuối cùng cho attempt đó.
- Nếu một attempt có nhiều bước thất bại, chỉ chọn một reason chính theo thứ tự pipeline.
- Đếm retry hoặc JWKS refresh riêng, không làm tăng giả số lượng validation attempt.
- Đếm request-level outcome riêng nếu một request có nhiều credential hoặc nhiều verifier.

### 3.2. Outcome tổng quát

Có thể dùng các outcome hữu hạn:

| Outcome | Ý nghĩa |
| --- | --- |
| accepted | Token vượt qua authentication validation. |
| rejected | Token hoặc proof không đáp ứng policy. |
| unavailable | Không thể hoàn tất một kiểm tra bắt buộc do dependency hoặc verifier failure. |
| skipped | Endpoint không yêu cầu token hoặc không có credential theo contract. |

Không dùng exception message hoặc chuỗi tùy ý làm outcome. Bộ giá trị phải ổn định để dashboard và alert có thể so sánh qua các phiên bản.

### 3.3. Reason code

Reason code mô tả bước đầu tiên khiến validation kết thúc:

~~~text
MALFORMED_TOKEN
UNSUPPORTED_ALGORITHM
KEY_NOT_FOUND
JWKS_UNAVAILABLE
SIGNATURE_INVALID
INVALID_ISSUER
INVALID_AUDIENCE
INVALID_TOKEN_TYPE
MISSING_REQUIRED_CLAIM
INVALID_CLAIM
EXPIRED
NOT_YET_VALID
REPLAY_DETECTED
SENDER_BINDING_FAILED
REVOCATION_CHECK_UNAVAILABLE
INTERNAL_VALIDATOR_ERROR
~~~

Đây là taxonomy minh họa. Hãy điều chỉnh theo token profile thực tế nhưng giữ số lượng reason code hữu hạn và định nghĩa rõ.

### 3.4. Thứ tự validation ảnh hưởng cách phân loại

Giả sử payload có audience sai và chữ ký cũng sai. Nếu verifier kiểm tra chữ ký trước, reason chính phải là SIGNATURE_INVALID; không thể kết luận audience check đã chạy.

Tương tự, token có kid không tồn tại thì verifier có thể dừng ở KEY_NOT_FOUND trước khi tới signature, issuer hoặc audience. Metric reason phải phản ánh bước thực sự kết thúc validation, không suy diễn từ payload chưa được xác minh.

## 4. Bộ metric nền tảng

Tên metric dưới đây là ví dụ trung lập nền tảng. Có thể biểu diễn bằng Prometheus, OpenTelemetry Metrics hoặc hệ thống telemetry khác; điều quan trọng là semantics, label và đơn vị đo nhất quán.

### 4.1. Tổng số validation attempts

~~~text
jwt_validation_attempts_total{
  profile,
  outcome,
  reason,
  issuer_alias,
  resource_alias
}
~~~

Counter này tăng một lần cho mỗi validation attempt kết thúc. Khi attempt accepted, reason có thể là none hoặc success theo schema thống nhất. Khi rejected/unavailable, reason là một giá trị hữu hạn trong taxonomy.

Không đưa raw issuer URI, raw audience, subject, jti hoặc token vào label.

### 4.2. Kết quả xác minh chữ ký

~~~text
jwt_signature_verifications_total{
  profile,
  outcome,
  algorithm
}
~~~

Metric này chỉ đếm các lần thực sự đi tới bước xác minh chữ ký. outcome có thể là valid hoặc invalid; lỗi key selection và lỗi thuật toán nên được đo riêng.

algorithm chỉ nên là giá trị allowlisted hoặc bucket bounded như allowed_rs256, allowed_es256, unsupported_algorithm. Không dùng chuỗi alg tùy ý từ token làm label vì attacker có thể tạo vô hạn giá trị.

### 4.3. Token hết hạn

~~~text
jwt_expired_tokens_total{
  profile,
  issuer_alias,
  resource_alias
}
~~~

Đếm attempt bị từ chối vì exp đã qua theo time policy. Không ghi exp chính xác hoặc token identity vào label.

Có thể bổ sung histogram:

~~~text
jwt_expiration_lateness_seconds
~~~

Histogram này đo khoảng thời gian token đã hết hạn tại thời điểm nhận, theo bucket cố định. Nó giúp phân biệt token vừa quá hạn do clock skew/client refresh chậm với token cũ nhiều giờ hoặc nhiều ngày. Chỉ thu thập khi có mục đích vận hành rõ; không ghi timestamp gốc.

### 4.4. Audience mismatch

~~~text
jwt_invalid_audience_total{
  profile,
  issuer_alias,
  resource_alias
}
~~~

Đếm token đã vượt qua các bước trước đó và bị từ chối do audience không dành cho resource hiện tại. resource_alias phải lấy từ cấu hình server, không lấy nguyên audience do token cung cấp.

### 4.5. Key không tìm thấy

~~~text
jwt_key_lookup_total{
  issuer_alias,
  result,
  source
}
~~~

result có thể là found, not_found, ambiguous, invalid_key hoặc unavailable. source có thể là trusted_cache hoặc trusted_jwks. Giá trị phải được chuẩn hóa và hữu hạn.

Metric tổng hợp:

~~~text
jwt_key_not_found_total{
  issuer_alias,
  profile
}
~~~

Chỉ tăng khi đã tra cứu trong key set gắn với issuer mà không tìm được khóa phù hợp sau quy trình refresh được phép. Nếu JWKS endpoint timeout, phân loại là JWKS_UNAVAILABLE thay vì KEY_NOT_FOUND.

### 4.6. JWKS refresh và cache

~~~text
jwt_jwks_refresh_total{
  issuer_alias,
  outcome
}

jwt_jwks_refresh_duration_seconds

jwt_jwks_cache_events_total{
  issuer_alias,
  result
}
~~~

Các cache result hữu ích:

- hit_fresh
- hit_stale_allowed
- miss
- refresh_success
- refresh_failure
- refresh_rate_limited
- unknown_kid

Không dùng kid làm label mặc định. Nếu cần điều tra một key cụ thể, dùng log/audit có kiểm soát với giá trị đã được giới hạn và không chứa secret.

### 4.7. Độ trễ xác minh

~~~text
jwt_validation_duration_seconds{
  profile,
  stage
}
~~~

stage có thể là parse, key_lookup, signature, claims, sender_proof hoặc total. Dùng histogram với bucket phù hợp để đo p50/p95/p99.

Không dùng subject, jti, token, raw path hoặc kid tùy ý làm label.

## 5. Định nghĩa tỷ lệ và denominator

Một dashboard chỉ có ý nghĩa khi numerator và denominator được định nghĩa rõ.

### 5.1. Tỷ lệ rejected

\[
RejectRate =
\frac{RejectedValidationAttempts}{AllValidationAttempts}
\]

Tỷ lệ này cho biết phần credential không vượt qua validation. Nó không phải tỷ lệ lỗi dịch vụ; một đợt token hết hạn hợp lệ về mặt vận hành vẫn làm reject rate tăng.

### 5.2. Tỷ lệ signature invalid

\[
SignatureFailureRate =
\frac{InvalidSignatureChecks}{CompletedSignatureChecks}
\]

Denominator là số lần thực sự thực hiện signature verification, không phải toàn bộ HTTP request. Token bị từ chối trước bước signature vì malformed hoặc key not found không thuộc denominator này.

### 5.3. Tỷ lệ expired

\[
ExpiredRate =
\frac{ExpiredTokenAttempts}{ValidationAttemptsWithTimeCheck}
\]

Có thể theo dõi thêm expired share trên rejected attempts để hiểu cơ cấu lỗi, nhưng phải đặt tên rõ. Hai tỷ lệ trả lời hai câu hỏi khác nhau.

### 5.4. Tỷ lệ audience mismatch

\[
AudienceMismatchRate =
\frac{AudienceMismatchAttempts}{AttemptsReachingAudienceValidation}
\]

Không chia cho tất cả request nếu nhiều request không có token hoặc bị từ chối ở bước trước.

### 5.5. Tỷ lệ key not found

\[
KeyNotFoundRate =
\frac{KeyLookupNotFound}{KeyLookupAttempts}
\]

Đồng thời theo dõi JWKS refresh failure và unknown-kid rate limit. Nếu key not found tăng cùng JWKS refresh failure, nguyên nhân có thể là key distribution hoặc network. Nếu key not found tăng với nhiều kid ngẫu nhiên trong khi JWKS khỏe, có thể là probing/unknown-kid storm.

### 5.6. Luôn hiển thị volume cùng rate

Một tỷ lệ 100% từ hai request có ý nghĩa khác tỷ lệ 5% trên hàng triệu request. Dashboard và alert nên hiển thị:

- Rate.
- Absolute count.
- Total validation volume.
- Baseline cùng khung thời gian.
- Breakdown theo profile/resource/issuer alias có cardinality được kiểm soát.

## 6. Thiết kế labels và kiểm soát cardinality

Metric labels tạo time series. Một label có nhiều giá trị khác nhau có thể làm hệ thống metrics tăng bộ nhớ, chi phí lưu trữ và độ trễ truy vấn.

### 6.1. Labels thường an toàn hơn khi có tập giá trị bounded

Ví dụ:

| Label | Giá trị phù hợp |
| --- | --- |
| profile | oauth_access_token, oidc_id_token, dpop_proof |
| outcome | accepted, rejected, unavailable |
| reason | taxonomy hữu hạn |
| issuer_alias | idp_primary, partner_alpha, workforce |
| resource_alias | billing_api, document_api, reporting_api |
| algorithm | allowlisted algorithm hoặc unsupported bucket |
| region | region code được cấu hình |
| verifier_version | release/version hữu hạn |
| stage | parse, key_lookup, signature, claims, total |

issuer_alias và resource_alias nên là tên nội bộ từ cấu hình, không phải giá trị URL tự do trong token.

### 6.2. Không đưa dữ liệu có cardinality cao vào labels

Tránh:

- Raw JWT hoặc Authorization header.
- sub, user ID, email hoặc account ID.
- jti hoặc token fingerprint.
- Raw kid do token gửi.
- Raw iss hoặc aud chưa xác minh.
- IP address hoặc User-Agent đầy đủ.
- URL path chứa resource ID.
- Exception message hoặc stack trace.
- Tên tenant do caller tự gửi nếu không có tập giới hạn.

Các giá trị này có thể tạo hàng triệu time series, làm lộ dữ liệu hoặc cho phép attacker gây cardinality explosion.

### 6.3. Phân biệt metrics, logs và traces

- **Metrics:** số liệu tổng hợp, bounded labels, dùng cho trend, dashboard và alert.
- **Logs:** sự kiện chi tiết có cấu trúc, dùng điều tra một request hoặc một key rotation.
- **Traces:** thời gian và dependency của một request qua các thành phần.

Không cố nhét toàn bộ ngữ cảnh vào metric label. Dùng correlation ID để liên kết log/trace trong phạm vi retention và privacy policy.

### 6.4. kid có cần theo dõi không?

kid hữu ích khi điều tra key rotation, nhưng không nên tự động trở thành label nếu giá trị đến từ token chưa tin cậy. Có thể:

- Đếm unknown_kid mà không giữ giá trị.
- Ghi kid đã chuẩn hóa trong log nội bộ với giới hạn độ dài và escaping.
- Chỉ gắn nhãn key_alias từ JWKS đã xác minh và registry có tập giá trị hữu hạn.
- Dùng sampling hoặc event riêng cho các trường hợp bất thường.

Không phản chiếu kid tùy ý vào metric label.

## 7. Đo và phân tích signature invalid

Signature invalid là một trong các tín hiệu quan trọng nhất vì nó có thể xuất hiện do token bị sửa, key sai, algorithm mismatch hoặc triển khai rotation chưa đồng bộ.

### 7.1. Nguyên nhân thường gặp

- Token bị thay đổi sau khi ký.
- Token được gửi tới sai issuer/verifier.
- Verifier dùng sai JWKS hoặc sai key do cache namespace không đúng.
- Issuer rotate signing key nhưng resource server chưa tải key mới.
- Issuer ngừng publish key cũ quá sớm trong khi token cũ vẫn còn hạn.
- Algorithm hoặc key type không tương thích.
- Token bị cắt, lỗi encoding hoặc signature segment malformed.
- Một bên ký và một bên xác minh diễn giải serialization khác nhau.
- Có hành vi token tampering hoặc thử nghiệm credential giả.

Không thể phân biệt chắc chắn attacker với client lỗi chỉ từ signature invalid. Cần correlation với key lookup, issuer, algorithm, release và nguồn request theo policy privacy.

### 7.2. Metric nên kết hợp

Theo dõi đồng thời:

- Signature verification invalid count/rate.
- Unsupported algorithm count.
- Key lookup not found.
- JWKS refresh count và failure.
- Key cache hit/miss.
- Token malformed count.
- Validation latency tại signature stage.
- Sự kiện key rotation và emergency revoke.

Nếu signature invalid tăng nhưng key lookup và JWKS đều ổn định, có thể là token tampering, client gửi token sai hoặc issuer signing mismatch. Nếu signature invalid tăng ngay sau rollout key, kiểm tra key selection và overlap.

### 7.3. Không giảm kiểm tra chữ ký để hạ metric

Không được:

- Bỏ qua signature verification khi JWKS lỗi.
- Thử tất cả khóa của mọi issuer.
- Cho phép thuật toán ngoài allowlist.
- Chấp nhận token chỉ vì payload đọc được.
- Dùng key cũ vô thời hạn mà không có policy.

Số signature failure giảm không phải mục tiêu nếu nó đạt được bằng cách chấp nhận token không xác minh được.

## 8. Đo và phân tích expired token

Expired token thường phản ánh vòng đời credential và đồng bộ client nhiều hơn là tấn công. Tuy nhiên, mức tăng bất thường có thể báo hiệu refresh flow lỗi, client lưu token cũ hoặc clock sai.

### 8.1. Phân nhóm theo độ trễ hết hạn

Histogram expiration lateness có thể phân biệt:

- Vừa quá hạn: có thể liên quan clock skew hoặc request đến sát thời điểm refresh.
- Quá hạn vài phút: client refresh chậm hoặc retry.
- Quá hạn lâu: token cũ bị lưu lại, session không được cập nhật hoặc client dùng nhầm cache.

Chỉ lưu bucket khoảng thời gian, không ghi exp chính xác hoặc token.

### 8.2. Metric bổ sung

- Expired token count/rate.
- Token gần hết hạn khi request bắt đầu, nếu có lý do vận hành để đo.
- Refresh token endpoint success/failure rate.
- Client refresh retry count.
- Clock offset của các verifier.
- Tỷ lệ token not-yet-valid.
- Validation time skew theo region.

Không nhất thiết mọi hệ thống cần tất cả metric. Chọn những tín hiệu có thể dẫn tới hành động cụ thể.

### 8.3. Nguyên nhân thường gặp

- Client không thay access token sau refresh.
- Nhiều tab hoặc process dùng token cũ.
- Refresh token đã hết hạn hoặc bị revoke.
- Client retry request với Authorization header cũ.
- Access token TTL thay đổi nhưng client cache không thích ứng.
- Clock verifier hoặc issuer bị lệch.
- Token được phát hành với exp sai.
- Request đi qua queue/proxy làm tăng thời gian chờ trước khi xác minh.

### 8.4. Clock skew cần đo, không nên nới tùy tiện

Một khoảng clock skew nhỏ có thể cần thiết cho sai lệch đồng hồ thực tế. Nhưng tăng leeway lớn để giảm expired rate làm kéo dài cửa sổ chấp nhận token đã hết hạn.

Khi expired tăng:

1. Đo clock offset giữa issuer và verifier.
2. Kiểm tra NTP/time synchronization.
3. Kiểm tra exp và TTL do issuer phát hành bằng test fixture an toàn.
4. Kiểm tra client refresh và token replacement.
5. Chỉ thay clock skew sau khi đánh giá tác động bảo mật và có giới hạn rõ.

## 9. Đo và phân tích invalid audience

Audience mismatch thường chỉ ra token đang được dùng ở resource server khác với recipient mà issuer đã định. Nó có thể do routing/configuration sai hoặc là dấu hiệu token substitution.

### 9.1. Nguyên nhân thường gặp

- Client yêu cầu token cho sai resource.
- API Gateway chuyển token dành cho Gateway tới backend.
- Service gọi downstream nhưng tái sử dụng access token có audience của upstream.
- Cấu hình audience ở issuer và resource server không thống nhất.
- Multi-tenant hoặc multi-environment mapping sai.
- Token bị gửi tới API khác do routing hoặc client bug.
- Attacker thử dùng token bị lấy từ resource server khác.

### 9.2. Metric nên kết hợp

- Audience mismatch count/rate theo resource_alias.
- Issuer alias.
- Token profile.
- Client application alias nếu có tập hữu hạn và được phép đo.
- Token exchange success/failure nếu kiến trúc sử dụng exchange.
- Route template và deployment version.

Không ghi raw aud chưa xác minh vào metric. Nếu cần biết audience thực tế trong điều tra, ghi sự kiện có kiểm soát sau khi xác minh chữ ký hoặc dùng bucket mismatch_class đã chuẩn hóa.

### 9.3. Không bỏ audience check để sửa lỗi routing

Không:

- Chấp nhận mọi audience từ cùng hostname.
- Dùng prefix match.
- Coi scope là audience.
- Cho backend chấp nhận token của Gateway.
- Chấp nhận audience của môi trường development tại production.

Hãy sửa resource indicator, issuer configuration, token exchange hoặc routing contract.

## 10. Đo và phân tích key not found

Key not found xảy ra khi verifier không tìm thấy JWK phù hợp với issuer, kid, algorithm và profile. Đây là tín hiệu cần phân tích cùng cache và JWKS refresh.

### 10.1. Phân biệt key not found và JWKS unavailable

| Tình huống | Reason chính | Ý nghĩa |
| --- | --- | --- |
| kid không có trong JWKS đã tải thành công | KEY_NOT_FOUND | Token dùng key không được issuer công bố hoặc key ID sai. |
| JWKS endpoint timeout khi cần key mới | JWKS_UNAVAILABLE | Verifier không thể lấy bằng chứng key mới. |
| JWKS response malformed | JWKS_INVALID | Nguồn key trả dữ liệu không thể tin cậy. |
| Có nhiều key phù hợp gây nhập nhằng | KEY_AMBIGUOUS | Key selection policy không xác định được duy nhất. |
| kid tìm thấy nhưng key type/alg không phù hợp | KEY_ALGORITHM_MISMATCH | Có key nhưng không thể dùng cho thuật toán/profile. |

Không gộp tất cả vào key_not_found_total; nếu gộp, đội vận hành có thể nhầm lỗi network với token dùng key lạ.

### 10.2. Nguyên nhân bình thường

- Issuer vừa rotate key và JWKS cache chưa refresh.
- Issuer publish key mới nhưng verifier chưa refresh.
- Token cũ dùng key đã bị loại khỏi JWKS quá sớm.
- kid bị cấu hình sai.
- Verifier đang trỏ tới sai issuer/JWKS.
- Cache namespace chỉ theo kid nên va chạm giữa issuer.

### 10.3. Nguyên nhân bất thường

- Attacker gửi nhiều kid ngẫu nhiên để kích hoạt JWKS refresh.
- Token giả mạo issuer hoặc key source.
- Có nỗ lực ép verifier fetch jku/x5u ngoài trust.
- JWKS response bị can thiệp hoặc DNS/TLS bị lỗi.
- Một issuer bị cấu hình nhầm hoặc metadata bị thay đổi ngoài quy trình.

### 10.4. Metric nên kết hợp

- Key lookup result.
- Unknown kid rate.
- JWKS refresh attempts/success/failure.
- Refresh latency.
- Cache hit/miss/stale.
- Refresh rate-limited count.
- JWKS response size và key count theo histogram/bucket nếu cần.
- Issuer metadata validation failures.

### 10.5. Không refresh JWKS vô hạn cho mỗi kid lạ

Một đợt kid ngẫu nhiên có thể tạo request storm tới issuer. Dùng single-flight, negative cache ngắn có kiểm soát, rate limit và giới hạn outbound concurrency. Các cơ chế này không được biến key không tìm thấy thành key hợp lệ.

## 11. Dashboard vận hành đề xuất

Một dashboard hữu ích nên cho phép người trực ca trả lời nhanh: có bao nhiêu validation attempt, tỷ lệ chấp nhận/từ chối ra sao, nhóm lỗi nào tăng, verifier có chậm không và trust dependency có khỏe không.

### 11.1. Tổng quan traffic và kết quả

Hiển thị:

- Validation attempts per second.
- Accepted/rejected/unavailable rate.
- Rejection count theo reason.
- Request thiếu credential nếu endpoint có yêu cầu đo.
- Authorization denied tách khỏi authentication rejected.

### 11.2. Breakdown theo nhóm lỗi

Hiển thị riêng:

- Signature invalid.
- Expired.
- Invalid audience.
- Key not found.
- Unsupported algorithm.
- Invalid issuer/type/claims.
- JWKS unavailable/invalid.
- Replay detected và sender binding failure nếu có.

Cho phép lọc theo issuer_alias, resource_alias, profile, region và release version trong giới hạn cardinality.

### 11.3. Key distribution và JWKS

Hiển thị:

- JWKS cache hit ratio.
- Refresh success/failure.
- Refresh duration.
- Unknown kid count.
- Rate-limited refresh.
- Key lookup not found.
- Metadata/JWKS TLS/DNS/network errors.

Khi deploy signing key mới, dashboard cần cho thấy các verifier đã nhận key mới và key cũ vẫn còn trong overlap theo kế hoạch.

### 11.4. Latency và resource usage

Hiển thị:

- Validation duration p50/p95/p99.
- Signature stage latency.
- Key lookup latency.
- JWKS refresh latency.
- CPU/memory của verifier.
- Request queue, worker saturation và outbound connection pool.
- Parser errors và input size buckets.

### 11.5. Dashboard phải hiển thị volume cùng tỷ lệ

Không chỉ vẽ percentage. Hiển thị số attempt tuyệt đối và tổng volume trong cùng panel để tránh diễn giải sai khi traffic thấp.

## 12. Alerting: cảnh báo theo xu hướng và tác động

Không nên alert chỉ vì một token sai. Credential lỗi là điều có thể xảy ra thường xuyên. Alert cần dựa vào mức tăng bất thường, tỷ lệ, volume, ảnh hưởng tới token hợp lệ và tình trạng dependency.

### 12.1. Signature failure spike

Điều kiện có thể xem xét:

- Signature failure rate tăng đáng kể so với baseline.
- Absolute count vượt mức tối thiểu.
- Tăng đồng thời ở nhiều resource server.
- Hoặc bắt đầu ngay sau signing-key rollout.

Điều tra key rotation, issuer, thuật toán, JWKS cache và token tampering.

### 12.2. Expired token spike

Alert khi expired rate tăng đột ngột hoặc tập trung ở một client/resource/region đã được chuẩn hóa. Kết hợp refresh endpoint failure và clock offset để tìm nguyên nhân.

Expired tăng đơn lẻ không nhất thiết là security incident; có thể là client release lỗi hoặc TTL configuration thay đổi.

### 12.3. Audience mismatch spike

Alert khi mismatch tăng trên một resource hoặc xuất hiện ở nhiều API không liên quan. Kiểm tra routing, token exchange, resource configuration và dấu hiệu token substitution.

Không hạ audience policy để làm alert biến mất.

### 12.4. Key not found và unknown-kid storm

Alert khi:

- Unknown kid rate vượt baseline.
- JWKS refresh rate tăng bất thường.
- Refresh bị rate limit liên tục.
- JWKS endpoint lỗi hoặc latency tăng.
- Key not found tăng sau rotation.

Nếu unknown kid tăng nhưng JWKS refresh thành công và traffic hợp lệ vẫn ổn, có thể là probing. Nếu refresh failure tăng cùng valid-token acceptance giảm, có thể là sự cố key distribution.

### 12.5. Alert cho dependency unavailable

JWKS, introspection, replay store hoặc certificate validation outage có thể làm token hợp lệ bị từ chối. Alert nên dựa trên dependency failure và synthetic valid-token check, không chỉ trên số invalid credential.

### 12.6. Tránh alert noise

- Dùng minimum volume threshold.
- Dùng rolling window và baseline theo giờ/ngày.
- Gộp alert cùng nguyên nhân.
- Có severity riêng cho credential anomaly và service availability.
- Có runbook link hoặc reason code.
- Tránh alert theo từng kid hoặc subject.
- Không để retry tạo hàng nghìn alert giống nhau.

## 13. Ví dụ truy vấn tỷ lệ bằng PromQL

Các truy vấn sau minh họa cách tính với metric schema ở trên. Tên label có thể cần điều chỉnh theo hệ thống thực tế.

### 13.1. Tỷ lệ signature failure trên signature checks

~~~promql
sum(rate(jwt_signature_verifications_total{outcome="invalid"}[5m]))
/
clamp_min(sum(rate(jwt_signature_verifications_total[5m])), 1)
~~~

### 13.2. Tỷ lệ expired trên validation attempts

~~~promql
sum(rate(jwt_expired_tokens_total[5m]))
/
clamp_min(sum(rate(jwt_validation_attempts_total[5m])), 1)
~~~

### 13.3. Tỷ lệ audience mismatch

Nếu có counter riêng cho audience validation attempts:

~~~promql
sum(rate(jwt_invalid_audience_total[5m]))
/
clamp_min(sum(rate(jwt_audience_checks_total[5m])), 1)
~~~

Nếu chưa có jwt_audience_checks_total, dùng validation attempts đã được gắn reason/stage tương ứng hoặc bổ sung metric stage. Không thay denominator bằng tổng HTTP request mà không giải thích.

### 13.4. Key lookup not found rate

~~~promql
sum(rate(jwt_key_lookup_total{result="not_found"}[5m]))
/
clamp_min(sum(rate(jwt_key_lookup_total[5m])), 1)
~~~

### 13.5. JWKS refresh failure rate

~~~promql
sum(rate(jwt_jwks_refresh_total{outcome="failure"}[5m]))
/
clamp_min(sum(rate(jwt_jwks_refresh_total[5m])), 1)
~~~

### 13.6. Validation latency p95

~~~promql
histogram_quantile(
  0.95,
  sum by (le, profile) (
    rate(jwt_validation_duration_seconds_bucket{stage="total"}[5m])
  )
)
~~~

Các truy vấn này chỉ có ý nghĩa nếu counter được cập nhật đúng một lần cho mỗi event, label bounded và denominator tương ứng với đúng stage.

## 14. SLI/SLO cho dịch vụ xác minh JWT

Không nên dùng tỷ lệ token hợp lệ làm SLO availability. Một đợt client gửi token sai có thể làm reject rate tăng dù verifier vẫn hoạt động bình thường.

### 14.1. SLI availability

Một SLI hữu ích có thể đo tỷ lệ validation attempt hợp lệ về mặt cấu hình được xử lý thành công mà không gặp lỗi nội bộ hoặc dependency bắt buộc.

Ví dụ:

\[
VerifierAvailability =
\frac{ValidTokenChecksCompletedSuccessfully}
{ValidTokenChecksExpected}
\]

Trong thực tế, khó biết mọi request đầu vào có token hợp lệ hay không nếu verifier không hoàn tất. Có thể dùng synthetic valid-token probes, canary token trong môi trường kiểm soát hoặc phân loại unavailable/internal error để ước lượng availability.

Không tính token expired hoặc wrong audience như lỗi availability của verifier.

### 14.2. SLI latency

Đo tỷ lệ validation attempts hoàn tất trong latency objective, tách theo profile hoặc resource nếu cần. Theo dõi p95/p99 và tail latency do JWKS refresh hoặc introspection.

### 14.3. SLI key distribution

Theo dõi thời gian từ lúc issuer publish key mới đến khi các verifier cần thiết có thể dùng key đó, cũng như tỷ lệ JWKS refresh thành công. Đây là tín hiệu quan trọng trong key rotation.

### 14.4. Đặt SLO theo khả năng vận hành

Ví dụ mục tiêu nội bộ:

- Phần lớn validation với key đã cache hoàn tất dưới một ngưỡng latency xác định.
- JWKS refresh thành công trong một tỷ lệ mục tiêu khi endpoint khỏe.
- Key mới được phân phối tới verifier trong một khoảng thời gian mục tiêu.
- Không có validation attempt nào được ALLOW khi signature hoặc required trust check thất bại.

Các con số cụ thể cần được xác định từ traffic, kiến trúc, threat model và cam kết dịch vụ. Không sao chép một threshold chung cho mọi hệ thống.

### 14.5. Security invariant không phải SLO có thể hy sinh

Không đặt SLO kiểu “tỷ lệ từ chối dưới 1%” nếu điều đó khuyến khích chấp nhận token sai. Security invariant như kiểm tra chữ ký, issuer, audience và token profile phải luôn đúng. SLO tối ưu độ sẵn sàng và độ trễ trong khi giữ invariant đó.

## 15. Logging, tracing và bảo vệ dữ liệu

Metrics giúp nhận ra xu hướng; logs và traces hỗ trợ điều tra. Vì JWT thường chứa định danh, quyền và credential bearer, telemetry phải tránh trở thành nguồn rò rỉ token.

### 15.1. Trường log có ích

Ví dụ event an toàn:

~~~json
{
  "event": "jwt_validation_rejected",
  "reason": "INVALID_AUDIENCE",
  "profile": "oauth_access_token",
  "issuer_alias": "identity_primary",
  "resource_alias": "billing_api",
  "verifier_version": "2026.11.16",
  "region": "region-a",
  "request_id": "req-7f3a",
  "validation_stage": "audience",
  "decision": "REJECT"
}
~~~

Đây là event minh họa. Không ghi raw token, Authorization header, refresh token, private key hoặc toàn bộ claims.

### 15.2. Không log raw JWT

JWT bearer là credential. Bất kỳ ai lấy được token còn hạn có thể thử sử dụng nó. Log có thể được lưu lâu, sao chép sang hệ thống phân tích hoặc truy cập bởi nhiều nhóm hơn hệ thống token.

Không ghi:

- Raw compact JWT.
- Refresh token.
- Authorization header.
- DPoP proof nguyên vẹn nếu không cần thiết.
- Private key hoặc client secret.
- Toàn bộ payload claims.

### 15.3. Correlation ID thay vì token ID

Ưu tiên request ID/correlation ID do hệ thống tạo để liên kết các log trong cùng request. Không cần dùng jti hoặc token fingerprint làm nhãn metric.

Nếu điều tra cần nhận diện cùng một token qua nhiều sự kiện, cân nhắc fingerprint HMAC có khóa bảo vệ, scope giới hạn, retention ngắn và quyền truy cập chặt. Hash thường của token vẫn có thể trở thành định danh ổn định và không nên phát tán tùy tiện.

### 15.4. Tránh log dữ liệu chưa xác minh

Claims trước khi chữ ký được xác minh là dữ liệu do caller kiểm soát. Không ghi chúng vào log như danh tính đáng tin. Nếu cần ghi dữ liệu đầu vào để debug parser, phải giới hạn độ dài, escape an toàn, loại bỏ credential và đặt quyền truy cập phù hợp.

### 15.5. Tracing không làm lộ token

Không đưa Authorization header hoặc JWT vào span attributes. Có thể ghi:

- validation profile.
- validation stage.
- outcome/reason code.
- issuer alias đã cấu hình.
- dependency operation và latency.

Không đưa sub, jti, raw kid hoặc raw audience vào trace attributes nếu không có lý do và kiểm soát privacy rõ.

## 16. Runbook: signature invalid tăng đột biến

Khi signature invalid tăng:

1. Xác nhận tổng validation volume có thay đổi hay không.
2. Xác định lỗi tăng ở một issuer/resource hay nhiều nơi.
3. Kiểm tra thời điểm deploy verifier, issuer hoặc signing-key rotation.
4. So sánh signature failure với key lookup, unknown kid và JWKS refresh.
5. Kiểm tra algorithm allowlist, key type và issuer-specific JWKS mapping.
6. Xác minh issuer có ký bằng key mới và public key đã được publish trước khi dùng không.
7. Kiểm tra overlap giữa key cũ và key mới có đủ cho token cũ còn hạn không.
8. Kiểm tra malformed/tampered token hoặc traffic probing.
9. Dùng test token ký bằng test key hoặc synthetic probe để xác nhận verifier.
10. Nếu nghi key compromise, kích hoạt quy trình key incident response và emergency revoke.

Không tắt signature verification, không chấp nhận mọi key và không mở rộng algorithm allowlist chỉ để khôi phục traffic.

## 17. Runbook: expired token tăng đột biến

Khi expired token tăng:

1. Kiểm tra tỷ lệ expired trên tổng validation và volume tuyệt đối.
2. Phân tích expiration lateness buckets.
3. So sánh theo client release, resource và region alias.
4. Kiểm tra refresh endpoint success/failure và retry.
5. Kiểm tra client có lưu access token cũ sau khi nhận token mới không.
6. Kiểm tra queue/proxy delay và clock offset giữa issuer/verifier.
7. Kiểm tra thay đổi TTL hoặc session lifetime gần đây.
8. Xác minh token được phát hành có exp đúng theo policy.
9. Khắc phục refresh/client lifecycle hoặc time synchronization.
10. Chỉ thay clock skew nếu có bằng chứng và đánh giá security impact.

Không tăng thời hạn token hoặc clock skew hàng loạt như một biện pháp chữa cháy mặc định.

## 18. Runbook: invalid audience tăng đột biến

Khi audience mismatch tăng:

1. Xác định resource_alias nào bị ảnh hưởng.
2. Kiểm tra thay đổi API routing, Gateway và service discovery.
3. Kiểm tra issuer resource mapping và client request resource indicator.
4. Xác định có downstream call tái sử dụng token upstream hay không.
5. Kiểm tra token exchange flow và audience của token downstream.
6. Kiểm tra multi-tenant hoặc môi trường dev/staging/prod mapping.
7. Xác minh token mẫu bằng test fixture được ký hợp lệ.
8. Đánh giá liệu có token substitution hoặc truy cập chéo API không.
9. Sửa cấu hình issuer/client/routing hoặc token exchange.
10. Giữ audience validation chính xác sau khi sửa.

Không bỏ audience check hoặc chấp nhận mọi audience cùng hostname.

## 19. Runbook: key not found và unknown-kid storm

Khi key not found tăng:

1. Phân biệt KEY_NOT_FOUND với JWKS_UNAVAILABLE, JWKS_INVALID và KEY_ALGORITHM_MISMATCH.
2. Kiểm tra issuer_alias và resource_alias bị ảnh hưởng.
3. Xem JWKS refresh có thành công không và độ trễ bao lâu.
4. Kiểm tra cache hit/miss, stale state và rate-limited refresh.
5. Kiểm tra issuer có publish kid mới trước khi bắt đầu ký bằng key mới không.
6. Xác minh JWKS có đúng issuer và TLS/DNS không có thay đổi bất thường.
7. Kiểm tra unknown kid có nhiều giá trị ngẫu nhiên hoặc tăng từ một nguồn traffic.
8. Kiểm tra single-flight, negative cache và outbound rate limit.
9. Nếu key mới hợp lệ, cập nhật trusted JWKS theo quy trình và xác minh rollout.
10. Nếu nghi key hoặc metadata bị compromise, kích hoạt trust/key incident response.

Không fetch jku/x5u từ token, không chọn key đầu tiên và không dùng key từ issuer khác để xử lý unknown kid.

## 20. Kiểm thử instrumentation và metric correctness

Metric sai có thể khiến alert và quyết định vận hành sai. Cần test instrumentation như một phần của verifier.

### 20.1. Kiểm tra mỗi attempt được đếm đúng một lần

- Token hợp lệ tăng accepted đúng một lần.
- Signature invalid tăng reason tương ứng đúng một lần.
- Expired tăng expired counter và rejected outcome.
- Audience mismatch tăng audience counter sau khi các bước trước đạt.
- Key not found tăng lookup result, không bị đếm thành signature invalid.
- JWKS timeout tăng unavailable/dependency failure.
- Authorization denial không tăng authentication failure.

### 20.2. Kiểm tra retry không làm sai denominator

Một request có thể retry JWKS fetch nhiều lần hoặc có nhiều network attempt. Các retry phải được đếm trong metric dependency/retry riêng. Không đếm mỗi retry thành một validation attempt mới nếu request vẫn là cùng một attempt.

Nếu client gửi lại HTTP request, đó là request/validation attempt mới và phải được đếm riêng.

### 20.3. Kiểm tra reason precedence

Tạo fixture lỗi nhiều điều kiện cùng lúc để xác nhận reason code phản ánh bước đầu tiên theo validation pipeline. Không suy ra audience mismatch từ payload chưa xác minh khi signature đã fail.

### 20.4. Kiểm tra cardinality

Gửi token với:

- Hàng nghìn kid ngẫu nhiên.
- iss/aud tùy ý.
- sub/jti ngẫu nhiên.
- URL path chứa ID khác nhau.
- User-Agent khác nhau.

Xác minh số time series không tăng theo từng giá trị đầu vào. Metric phải gom vào bounded buckets.

### 20.5. Kiểm tra không rò rỉ credential

Gửi token lỗi và kiểm tra log, trace, error report, metric exemplar và dead-letter queue. Không được có raw JWT, refresh token, Authorization header hoặc private key.

## 21. Kiểm thử tải và fault injection

### 21.1. Load test với token hợp lệ

Đo:

- Throughput validation.
- p50/p95/p99 latency.
- CPU và memory.
- Cache hit ratio.
- Signature verification cost.
- JWKS refresh behavior khi key đã cache.

### 21.2. Load test với token lỗi

Gửi tỷ lệ có kiểm soát các token malformed, expired, wrong audience, invalid signature và unknown kid. Quan sát:

- Parser CPU/memory.
- Error counter rate.
- JWKS refresh storm.
- Log volume.
- Rate limiting.
- Thread/worker saturation.

Token lỗi không nên khiến verifier hoặc telemetry backend bị DoS.

### 21.3. Fault injection

Lần lượt làm các dependency:

- JWKS endpoint timeout hoặc trả JSON malformed.
- DNS/TLS lookup thất bại.
- Clock source lệch hoặc unavailable.
- Introspection endpoint timeout.
- Replay store không ghi được.
- Cache bị mất hoặc stale.
- Crypto provider/key store lỗi.

Kết quả cần:

- Không ALLOW khi thiếu bằng chứng bắt buộc.
- Metric phân biệt credential invalid với dependency unavailable.
- Alert được kích hoạt đúng mức.
- Không có retry storm hoặc cardinality explosion.
- Log không lộ token.

## 22. Ví dụ taxonomy cấu hình telemetry

Một cấu hình khái niệm có thể định nghĩa reason code và label allowlist:

~~~yaml
jwt_observability:
  outcomes:
    - accepted
    - rejected
    - unavailable

  reasons:
    - malformed_token
    - unsupported_algorithm
    - key_not_found
    - jwks_unavailable
    - jwks_invalid
    - signature_invalid
    - invalid_issuer
    - invalid_audience
    - invalid_token_type
    - missing_required_claim
    - invalid_claim
    - expired
    - not_yet_valid
    - replay_detected
    - sender_binding_failed
    - revocation_check_unavailable
    - internal_validator_error

  bounded_labels:
    - profile
    - outcome
    - reason
    - issuer_alias
    - resource_alias
    - region
    - verifier_version
    - validation_stage

  forbidden_labels:
    - raw_token
    - authorization_header
    - subject
    - jti
    - raw_kid
    - raw_issuer
    - raw_audience
    - exception_message

  counters:
    - jwt_validation_attempts_total
    - jwt_signature_verifications_total
    - jwt_expired_tokens_total
    - jwt_invalid_audience_total
    - jwt_key_lookup_total
    - jwt_jwks_refresh_total

  histograms:
    - jwt_validation_duration_seconds
    - jwt_jwks_refresh_duration_seconds
    - jwt_expiration_lateness_seconds
~~~

Đây là ví dụ thiết kế, không phải schema bắt buộc của một telemetry product. Tên metric và reason code phải được version hóa để thay đổi không làm hỏng dashboard hoặc alert hiện có.

## 23. Những lỗi thường gặp khi vận hành

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gộp mọi lỗi vào invalid_token | Không phân biệt token sai với dependency outage. | Reason taxonomy và outcome riêng. |
| Đếm mọi HTTP 401 là JWT failure | Có thể gồm thiếu credential hoặc policy khác. | Instrument validation stage cụ thể. |
| Không định nghĩa denominator | Tỷ lệ giữa dashboard không thể so sánh. | Định nghĩa attempts/checks theo stage. |
| Chỉ hiển thị percentage | Tỷ lệ cao từ traffic rất thấp gây hiểu sai. | Hiển thị count, rate và volume cùng nhau. |
| Dùng raw kid/iss/aud làm label | Cardinality explosion và lộ dữ liệu. | Alias bounded, bucket và log có kiểm soát. |
| Đếm JWKS retry thành validation attempt | Làm sai tỷ lệ lỗi. | Metric retry/dependency riêng. |
| Coi key not found là signature invalid | Che giấu lỗi key distribution hoặc unknown-kid storm. | Phân biệt key lookup với signature verification. |
| Coi JWKS timeout là key not found | Nhầm outage với token dùng key không được công bố. | Reason code JWKS_UNAVAILABLE. |
| Tăng clock skew khi expired tăng | Mở rộng thời gian chấp nhận token hết hạn. | Điều tra clock và refresh lifecycle trước. |
| Bỏ audience check để giảm 401 | Token có thể được dùng chéo resource. | Sửa resource mapping/token exchange. |
| Tắt signature verification khi JWKS lỗi | Chấp nhận token không có bằng chứng chữ ký. | Dùng cache chỉ theo trust/freshness policy; nếu không có key thì reject. |
| Alert theo từng subject hoặc kid | Alert noise, cardinality và lộ dữ liệu. | Alert theo bounded alias/reason và volume. |
| Log raw JWT để debug | Log trở thành kho credential. | Log reason code và correlation ID. |
| Đặt SLO theo reject rate | Khuyến khích nới validation để đạt SLO. | SLO availability/latency tách khỏi credential rejection. |

## 24. Checklist thiết kế observability cho JWT

Trước khi đưa metric và alert vào production, hãy xác nhận:

1. **Attempt definition:** một validation attempt được đếm ở đâu và khi nào?
2. **Outcome:** accepted, rejected, unavailable được phân biệt rõ chưa?
3. **Reason taxonomy:** signature, expired, audience, key not found và dependency failure có reason riêng không?
4. **Stage precedence:** reason phản ánh bước validation thực sự kết thúc không?
5. **Denominator:** tỷ lệ signature/expired/audience/key lookup dùng đúng số lần kiểm tra tương ứng không?
6. **Volume:** dashboard có count và rate cùng nhau không?
7. **Labels:** label có bounded values và không chứa dữ liệu từ token tùy ý không?
8. **Signature:** có metric invalid signature, unsupported algorithm và key lookup riêng không?
9. **Expiration:** có đo expired rate, lateness buckets và clock offset khi cần không?
10. **Audience:** mismatch được gắn với resource alias, không ghi raw audience vào metric không?
11. **Key lookup:** key not found được phân biệt với JWKS unavailable/invalid không?
12. **JWKS:** có cache hit/miss, refresh result, latency và rate-limit metric không?
13. **Latency:** có histogram tổng và theo stage không?
14. **Alerts:** alert dựa trên baseline, volume, impact và dependency health không?
15. **SLI/SLO:** credential rejection có tách khỏi verifier availability không?
16. **Privacy:** log/trace không chứa raw JWT, Authorization header, refresh token hoặc secret không?
17. **Instrumentation tests:** mỗi attempt và retry được đếm đúng không?
18. **Cardinality tests:** kid, iss, aud, sub và URL tùy ý không tạo time series mới không kiểm soát không?
19. **Runbooks:** mỗi alert có hướng điều tra và hành động an toàn không?
20. **Fail-closed:** lỗi metric, log hoặc dependency không làm thay đổi quyết định xác minh token không?

## 25. Ghi nhớ trọng tâm

- Signature invalid, expired, invalid audience và key not found là bốn nhóm tín hiệu khác nhau; cần metric riêng và reason code rõ.
- Phân biệt credential invalid với JWKS/introspection/replay dependency unavailable và internal verifier error.
- Một validation attempt cần được đếm đúng một lần; JWKS retry và request retry có metric riêng.
- Tỷ lệ phải dùng denominator theo đúng validation stage, đồng thời hiển thị volume tuyệt đối.
- Key not found khác JWKS unavailable: một trường hợp không có key phù hợp trong key set tin cậy, trường hợp kia không lấy được bằng chứng key.
- Expired rate tăng có thể do client refresh, clock skew, TTL hoặc token cũ; không tự động tăng clock leeway.
- Audience mismatch thường liên quan resource mapping, Gateway/backend hoặc token substitution; không bỏ audience check.
- Signature failure cần phân tích cùng key lookup, JWKS refresh, algorithm và key rotation; không bao giờ tắt signature verification để giảm metric.
- Labels phải bounded; không đưa raw token, sub, jti, kid tùy ý, issuer hoặc audience chưa xác minh vào metric labels.
- SLO availability/latency phải tách khỏi tỷ lệ credential rejection; security invariant luôn được giữ.
- Logs/traces dùng reason code và correlation ID, không ghi raw credential.
- Dashboard, alert và runbook cần kết hợp metric, deployment, key rotation, dependency health và synthetic valid-token probes.

**Tài liệu tham khảo kỹ thuật:** RFC 7517 (JSON Web Key); RFC 7519 (JSON Web Token); RFC 8725 (JSON Web Token Best Current Practices); RFC 9068 (JWT Profile for OAuth 2.0 Access Tokens); RFC 7662 (OAuth 2.0 Token Introspection); RFC 8414 (OAuth 2.0 Authorization Server Metadata). Các chuẩn này định nghĩa token, key, profile và introspection; taxonomy metric, dashboard, SLI/SLO và runbook cần được cụ thể hóa theo kiến trúc và chính sách vận hành của hệ thống.
