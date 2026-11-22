# Đọc tiêu chuẩn JWT, bộ JOSE, hướng dẫn thực hành và hồ sơ giao thức

## 1. Vì sao cần đọc tiêu chuẩn theo một phương pháp?

JWT và JOSE thường được giới thiệu bằng ví dụ ngắn: tạo payload JSON, ký bằng khóa rồi gửi token qua HTTP. Ví dụ giúp hiểu cú pháp nhưng chưa đủ để xây dựng hệ thống liên thông và an toàn.

Một hệ thống thực tế có thể đồng thời phụ thuộc vào định dạng token, cơ chế chữ ký/mã hóa, cấu trúc khóa, quy tắc kiểm tra issuer/audience, profile OAuth hoặc OpenID Connect, quy tắc vận chuyển credential, đăng ký IANA và hướng dẫn bảo mật được cập nhật sau khi tiêu chuẩn nền tảng công bố.

Nếu chỉ đọc RFC JWT mà không đọc profile giao thức, consumer có thể parse và verify chữ ký thành công nhưng vẫn chấp nhận sai loại token, sai audience hoặc sai ngữ nghĩa authorization. Nếu chỉ làm theo tài liệu thư viện, hệ thống có thể phụ thuộc vào default và hành vi riêng của thư viện, dẫn đến khác biệt giữa các triển khai.

**Đọc tiêu chuẩn đúng cách** là xác định hợp đồng giao thức cần tuân theo, tìm tài liệu phụ thuộc có tính quy phạm, hiểu yêu cầu bắt buộc và khuyến nghị, rồi kiểm chứng bằng test vector và thử nghiệm liên thông.

Phạm vi bài này là kiến thức JWT/JOSE và tiêu chuẩn giao thức dùng chung, không phụ thuộc ngôn ngữ lập trình, framework hoặc thư viện cụ thể.

## 2. Phân biệt các loại nguồn tài liệu

Không phải tài liệu nào có từ JWT hoặc OAuth trong tiêu đề cũng có cùng thẩm quyền. Trước khi dùng một tài liệu để quyết định hành vi bảo mật, cần xác định nguồn và trạng thái của nó.

| Nguồn | Vai trò | Cách sử dụng |
| --- | --- | --- |
| RFC được xuất bản | Đặc tả giao thức hoặc hướng dẫn đã công bố trong chuỗi RFC | Đọc nội dung chuẩn, trạng thái, cập nhật và errata |
| IETF Datatracker | Theo dõi quá trình phát triển, quan hệ giữa RFC/draft và trạng thái tài liệu | Xác minh tài liệu đã xuất bản hay còn là draft; tìm RFC cập nhật/thay thế |
| IANA registries | Danh mục giá trị đã đăng ký cho JOSE, JWT, OAuth và giao thức liên quan | Tra cứu identifier, trạng thái đăng ký, tài liệu tham chiếu |
| Đặc tả của tổ chức tiêu chuẩn khác | Định nghĩa profile hoặc giao thức không nằm trong một RFC cụ thể | Ví dụ OpenID Connect Core do OpenID Foundation công bố |
| Hướng dẫn nhà cung cấp | Giải thích cách một sản phẩm hoặc thư viện triển khai giao thức | Dùng để hiểu triển khai; đối chiếu với tiêu chuẩn gốc |
| Blog và bài hướng dẫn cộng đồng | Giải thích, ví dụ và kinh nghiệm | Dùng để học hoặc tìm từ khóa; không coi là nguồn quy phạm |

Các nguồn chính thức nên ưu tiên:

- [RFC Editor](https://www.rfc-editor.org/) — bản RFC đã xuất bản.
- [IETF Datatracker](https://datatracker.ietf.org/) — trạng thái, lịch sử và quan hệ tài liệu.
- [IANA JOSE Registries](https://www.iana.org/assignments/jose/jose.xhtml) — registry thuật toán, khóa và header JOSE.
- [IANA JWT Claims Registry](https://www.iana.org/assignments/jwt/jwt.xhtml) — registered claims và JWT types.
- [IANA OAuth Parameters](https://www.iana.org/assignments/oauth-parameters/oauth-parameters.xhtml) — OAuth parameters.
- [OpenID Connect Specifications](https://openid.net/developers/specs/) — đặc tả OpenID Connect.

Không dùng bản sao RFC trên blog hoặc gist làm nguồn cuối cùng khi nội dung chính thức có thể tra cứu. Bản tóm tắt có thể bỏ qua normative language, errata hoặc security considerations.

## 3. Hiểu trạng thái và quan hệ giữa các RFC

Số RFC tăng dần theo thời gian, nhưng RFC có số lớn hơn không tự động thay thế RFC có số nhỏ hơn. Một tài liệu có thể cập nhật một phần, bổ sung profile hoặc chỉ tham chiếu tài liệu cũ.

Khi mở trang RFC, kiểm tra:

- **Status/category:** Standards Track, Best Current Practice (BCP), Informational, Experimental hoặc Historic.
- **Obsoletes:** RFC nào bị tài liệu này thay thế.
- **Obsoleted by:** tài liệu nào đã thay thế RFC đang đọc.
- **Updates:** RFC nào được tài liệu này cập nhật.
- **Updated by:** tài liệu nào cập nhật RFC đang đọc.
- **Errata:** lỗi biên tập hoặc kỹ thuật đã được báo cáo và trạng thái xử lý.
- **Normative references:** tài liệu cần đọc để hiểu hoặc tuân thủ yêu cầu.
- **Informative references:** tài liệu cung cấp bối cảnh hoặc giải thích.

### Phân biệt các trạng thái thường gặp

- **Standards Track:** đặc tả tiêu chuẩn giao thức hoặc cơ chế kỹ thuật.
- **BCP:** hướng dẫn thực hành tốt nhất trong một lĩnh vực; thường rất quan trọng cho vận hành và bảo mật.
- **Informational:** cung cấp thông tin hoặc mô tả; không mặc định tạo yêu cầu triển khai như Standards Track.
- **Experimental:** mô tả công nghệ hoặc cách tiếp cận đang thử nghiệm.
- **Historic:** tài liệu không còn được khuyến nghị sử dụng như tiêu chuẩn hiện hành.

Trạng thái không thay thế việc đọc nội dung. RFC Standards Track có thể định nghĩa cơ chế nền tảng, trong khi BCP sau này giải thích cách dùng cơ chế đó an toàn. Cả hai có thể cùng cần thiết.

### Errata và cập nhật

Errata có thể là lỗi biên tập, lỗi kỹ thuật hoặc vấn đề chưa được chấp nhận. Không phải mọi erratum được báo cáo đều đã được xác nhận. Kiểm tra trạng thái verified, rejected hoặc held for document update trên nguồn chính thức.

Khi một RFC được cập nhật, không mặc định toàn bộ văn bản cũ đã bị thay thế. Đọc quan hệ tài liệu và nội dung cập nhật để xác định chính xác yêu cầu bị ảnh hưởng.

## 4. Bản đồ tiêu chuẩn JWT và JOSE

JWT là định dạng claims; JOSE là bộ đặc tả cơ chế bảo vệ và biểu diễn đối tượng JSON. Các tài liệu liên quan được chia thành nhiều phần.

| Tài liệu | Phạm vi | Câu hỏi cần trả lời |
| --- | --- | --- |
| RFC 7519 — JWT | Cấu trúc JWT, registered claims và cách diễn giải | Payload có cấu trúc gì? Claim có nghĩa gì? |
| RFC 7515 — JWS | JSON Web Signature | Signing input, protected header và chữ ký được tạo/xác minh ra sao? |
| RFC 7516 — JWE | JSON Web Encryption | Plaintext được mã hóa và xác thực ra sao? |
| RFC 7517 — JWK | JSON Web Key | Khóa được biểu diễn và phân phối thế nào? |
| RFC 7518 — JWA | JSON Web Algorithms | Tên thuật toán và tham số JOSE có ý nghĩa gì? |
| RFC 7797 | JWS Unencoded Payload Option | Trường hợp nào payload JWS không được Base64url encode? |
| RFC 8037 | ECDH và EdDSA trong JOSE | Các thuật toán/curve bổ sung được biểu diễn ra sao? |
| RFC 8725 — JWT BCP | Hướng dẫn bảo mật JWT | Làm thế nào tránh các cách triển khai JWT nguy hiểm? |

Các RFC nền tảng cần được đọc như một bộ có liên hệ. Để hiểu JWS ký bằng khóa công khai, cần hiểu JWS serialization, thuật toán JWA và cách JWK biểu diễn public key. Để hiểu JWE, cần đọc cấu trúc JWE, thuật toán key management/content encryption và quy tắc xử lý header.

### JWT không đồng nghĩa với JWS

JWT có thể được biểu diễn bằng JWS hoặc JWE. JWS cung cấp tính toàn vẹn và xác thực nguồn theo mô hình khóa được sử dụng; payload JWS dạng thông thường không được mã hóa và có thể đọc được. JWE cung cấp bảo mật nội dung bằng mã hóa có xác thực theo cấu hình thuật toán.

Nested JWT có thể dùng JWS và JWE lồng nhau. Consumer cần biết profile mong đợi cấu trúc nào và thứ tự xử lý ra sao. Không tự động chấp nhận mọi serialization chỉ vì thư viện có thể parse chúng.

### JWK và JWKS

JWK biểu diễn một khóa; JWKS là một tập khóa JWK. Cần hiểu các trường như `kty`, `use`, `key_ops`, `alg`, `kid` và tham số khóa theo loại key.

- `kty` mô tả loại khóa.
- `use` gợi ý mục đích sử dụng như ký hoặc mã hóa.
- `key_ops` mô tả thao tác được phép theo biểu diễn khóa.
- `alg` có thể ràng buộc khóa với thuật toán dự kiến.
- `kid` là định danh hỗ trợ chọn khóa trong một tập khóa.

Không phải mọi trường đều bắt buộc trong mọi JWK. Consumer cần áp dụng profile và trust configuration, không chỉ kiểm tra JSON parse thành công.

## 5. Đọc JWT Best Current Practices cùng RFC nền tảng

RFC 8725 — JSON Web Token Best Current Practices (JWT BCP) là tài liệu quan trọng khi thiết kế và đánh giá triển khai JWT. Đọc RFC 7519 để hiểu định dạng, nhưng cần dùng JWT BCP để kiểm tra cách áp dụng an toàn.

Khi đọc BCP, tập trung vào:

- **Algorithm verification:** giới hạn thuật toán theo policy; không tin mù quáng giá trị do token cung cấp.
- **Cryptographic input validation:** xử lý đúng dữ liệu JOSE, khóa và thuật toán.
- **Issuer and audience validation:** kiểm tra issuer tin cậy và audience dành cho resource hiện tại.
- **Explicit typing:** phân biệt các loại JWT để tránh nhầm token giữa các mục đích.
- **Mutually exclusive validation rules:** các loại token có quy tắc xác minh khác nhau không nên dùng chung một validator mơ hồ.
- **Indirect attacks:** tránh nguồn khóa, URL hoặc tham số trong token khiến verifier thực hiện hành động ngoài trust boundary.
- **Compression and privacy:** đánh giá rò rỉ thông tin và side-channel khi có nén.

Một JWT có JSON hợp lệ, chữ ký đúng và claims parse được nhưng vẫn không an toàn nếu consumer chấp nhận thuật toán ngoài allowlist, không kiểm tra `iss`/`aud`, dùng ID Token như access token, hoặc để header khiến verifier tải khóa từ host không được tin cậy. Các vấn đề này nằm ở cách xác minh và profile, không chỉ ở cấu trúc JSON.

## 6. Đọc profile giao thức thay vì áp dụng JWT chung chung

RFC 7519 mô tả JWT tổng quát. Nó không tự định nghĩa mọi yêu cầu của OAuth access token, OpenID Connect ID Token hoặc DPoP proof. Khi JWT được dùng trong một giao thức, profile của giao thức xác định thêm yêu cầu.

| Profile/giao thức | Tài liệu tiêu biểu | Điều cần đọc |
| --- | --- | --- |
| OAuth 2.0 Framework | RFC 6749 | Vai trò authorization server/resource server, token endpoint và grant |
| OAuth Bearer Token | RFC 6750 | Cách gửi bearer token, error code và WWW-Authenticate |
| OAuth 2.0 Security BCP | RFC 9700 | Các thực hành bảo mật OAuth hiện hành |
| JWT Access Token Profile | RFC 9068 | Claims và yêu cầu validation riêng cho JWT access token |
| OpenID Connect Core | OpenID Connect Core 1.0 | ID Token, Authentication Request/Response, nonce, issuer, audience và validation |
| Authorization Server Metadata | RFC 8414 | Discovery metadata và endpoint/algorithm metadata |
| DPoP | RFC 9449 | Proof-of-possession, binding token và replay protection |
| OAuth mTLS | RFC 8705 | Client certificate authentication và certificate-bound token |

Các profile này không thể thay thế lẫn nhau:

- JWT access token theo RFC 9068 là credential dành cho resource server.
- ID Token của OpenID Connect cung cấp thông tin về kết quả xác thực người dùng cho client OIDC.
- DPoP proof là JWT có cấu trúc và quy tắc riêng; nó không phải access token.
- JWT assertion trong OAuth extension có thể có profile và audience khác.

Consumer phải biết endpoint đang nhận loại token nào và dùng đúng validator tương ứng.

### Ví dụ: xác minh JWT access token OAuth

Khi một API nhận OAuth JWT access token, bộ tài liệu thường cần xem xét gồm:

1. RFC 6749 để hiểu vai trò và luồng OAuth.
2. RFC 6750 để hiểu cách client gửi bearer credential và response lỗi.
3. RFC 7519 để hiểu JWT claims.
4. RFC 7515 và RFC 7518 cho JWS và thuật toán ký được dùng.
5. RFC 7517 để hiểu JWK/JWKS và chọn khóa.
6. RFC 8725 cho các nguyên tắc bảo mật JWT.
7. RFC 9068 cho profile JWT access token.
8. RFC 9700 cho hướng dẫn bảo mật OAuth hiện hành.

Đây là danh sách đọc theo nhu cầu; kiểm tra normative references và profile thực tế để xác định chính xác tài liệu nào bắt buộc cho triển khai cụ thể.

## 7. Cách đọc một RFC có hệ thống

Không nên bắt đầu bằng cách đọc từng dòng mà chưa xác định câu hỏi. Một quy trình thực tế:

1. **Abstract và Status:** tài liệu giải quyết vấn đề gì, phạm vi nào và trạng thái xuất bản ra sao; phân biệt RFC với Internet-Draft.
2. **Introduction và Scope:** xác định đối tượng áp dụng như issuer, client, resource server, verifier hoặc key provider; ghi lại vấn đề tài liệu không giải quyết.
3. **Terminology và Conventions:** tìm định nghĩa issuer, audience, subject, client, resource, protected header, recipient, key management và content encryption.
4. **Normative requirements:** tìm MUST, MUST NOT, REQUIRED, SHOULD, SHOULD NOT, MAY và OPTIONAL; ghi actor, điều kiện, ngoại lệ và hệ quả.
5. **Security Considerations:** đọc threat model, giả định tin cậy, side-channel, replay, key compromise, downgrade, parsing ambiguity và xử lý lỗi.
6. **IANA Considerations:** xác định thuật toán, claim, media type, header parameter hoặc protocol parameter được đăng ký.
7. **Normative References và Updates:** lập danh sách tài liệu phụ thuộc; một yêu cầu có thể được định nghĩa ở RFC khác.
8. **Examples và Appendices:** dùng ví dụ để hiểu serialization và luồng xử lý; ví dụ không thay thế normative requirements.

### Hiểu đúng từ ngữ quy phạm

RFC thường dùng từ khóa quy phạm theo RFC 2119 và RFC 8174. Khi các từ khóa được viết IN HOA trong ngữ cảnh quy phạm, chúng mang ý nghĩa cụ thể.

| Từ khóa | Cách hiểu |
| --- | --- |
| MUST / REQUIRED / SHALL | Yêu cầu bắt buộc trong phạm vi điều kiện được mô tả |
| MUST NOT / SHALL NOT | Điều bị cấm trong phạm vi điều kiện được mô tả |
| SHOULD / RECOMMENDED | Có thể có lý do hợp lệ để không làm, nhưng cần hiểu và cân nhắc đầy đủ hệ quả |
| SHOULD NOT / NOT RECOMMENDED | Có thể có trường hợp ngoại lệ, nhưng cần hiểu rủi ro khi thực hiện |
| MAY / OPTIONAL | Tùy chọn, trừ khi profile bổ sung yêu cầu khác |

Nếu RFC nói SHOULD, tìm lý do và ngoại lệ trong tài liệu. Một triển khai có thể chọn cách khác khi có lý do cụ thể, nhưng phải đánh giá tương tác với peer và rủi ro bảo mật. Ngược lại, không hạ MUST thành khuyến nghị chỉ vì thư viện đang dùng không hỗ trợ.

Một câu quy phạm thường chỉ áp dụng cho một vai trò. Yêu cầu dành cho issuer không tự động trở thành trách nhiệm của resource server. Khi lập checklist, ghi rõ actor và điều kiện.

## 8. Tra cứu IANA JOSE và JWT registries

IANA registries là danh mục có thẩm quyền cho các giá trị đã đăng ký. Chúng hữu ích khi triển khai cần trao đổi với nhiều thư viện hoặc tổ chức.

Các registry quan trọng gồm:

- JSON Web Signature and Encryption Algorithms.
- JSON Web Key Types.
- JSON Web Key Elliptic Curve.
- JSON Web Key Use.
- JSON Web Key Operations.
- JSON Web Signature and Encryption Header Parameters.
- JSON Web Token Claims.
- JSON Web Token Types.
- OAuth Authorization Server Metadata và OAuth parameters.

Với mỗi giá trị registry, kiểm tra tên identifier chính xác, ý nghĩa và tham số, RFC hoặc tài liệu đăng ký, trạng thái/ghi chú, điều kiện profile và khả năng tương thích với loại khóa.

Đăng ký trong IANA không có nghĩa thuật toán đó luôn an toàn hoặc được mọi profile khuyến nghị. Registry có thể giữ tên lịch sử để tương thích. Đối chiếu với JWT BCP, profile giao thức và chính sách thuật toán hiện hành.

Việc token khai báo `alg` không đủ để consumer chấp nhận thuật toán đó. Verifier phải có allowlist theo issuer/profile, kiểm tra loại khóa và áp dụng policy. Không để token tự quyết định thuật toán hoặc ép verifier chuyển từ thuật toán bất đối xứng sang MAC bằng cách tái sử dụng sai loại key.

Tương tự, `kid` chỉ hỗ trợ định vị khóa trong tập tin cậy; nó không làm cho một khóa bất kỳ trở thành khóa tin cậy.

## 9. Đọc hồ sơ giao thức theo ma trận yêu cầu

Khi một tổ chức chọn profile, hãy chuyển yêu cầu trong tài liệu thành ma trận có thể kiểm tra. Ví dụ cho access token:

| Nhóm | Câu hỏi phải trả lời | Bằng chứng cần có |
| --- | --- | --- |
| Issuer | Issuer nào được tin cậy? | Allowlist/trust configuration |
| Audience | Token phải dành cho resource nào? | Audience contract và negative tests |
| Token type | Đây là access token, ID token hay assertion? | Profile/type validation |
| Claims | Claim nào bắt buộc, tùy chọn, bị cấm? | Schema contract |
| JOSE | Serialization và thuật toán nào được phép? | Algorithm allowlist |
| Keys | Khóa lấy từ nguồn nào, rotation ra sao? | JWKS/key management policy |
| Time | `exp`, `nbf`, `iat` được kiểm tra thế nào? | Lifetime và clock skew policy |
| Replay | Credential có thể được dùng lại không? | `jti`, nonce, replay store hoặc sender constraint theo profile |
| Transport | Credential được gửi qua header, body hay cơ chế khác? | Protocol transport rules |
| Error | Token sai, thiếu quyền và dependency lỗi trả ra sao? | Error mapping contract |
| Extensions | Unknown header/claim được xử lý thế nào? | Critical parameter/unknown claim policy |
| Operations | Log, metrics, incident response ra sao? | Runbook và observability controls |

Ma trận cần ghi rõ yêu cầu nào đến từ RFC nền tảng, yêu cầu nào đến từ profile và yêu cầu nào là policy nội bộ. Không gộp tất cả vào một cột “JWT standard” vì sẽ khó truy nguyên khi cần thay đổi.

## 10. Phân biệt tiêu chuẩn với policy của tổ chức

Tiêu chuẩn thường định nghĩa nhiều lựa chọn để phục vụ môi trường khác nhau. Một tổ chức phải chọn tập con rõ ràng và có thể chặt chẽ hơn tiêu chuẩn.

Ví dụ policy nội bộ có thể chỉ chấp nhận một số signing algorithms đã phê duyệt, bắt buộc audience đơn cho API cụ thể, giới hạn maximum token lifetime, bắt buộc token type riêng, không cho phép một số serialization hoặc bắt buộc kiểm tra revocation cho giao dịch nhạy cảm.

Cần phân biệt ba lớp:

1. **Protocol requirement:** yêu cầu được tài liệu quy phạm định nghĩa.
2. **Profile requirement:** yêu cầu bổ sung để một loại token được dùng đúng trong giao thức cụ thể.
3. **Local policy:** lựa chọn và giới hạn của tổ chức hoặc hệ thống.

Khi ghi tài liệu thiết kế, gắn nguồn cho từng yêu cầu. Nếu policy nội bộ chặt hơn RFC, ghi rõ đó là policy để không tuyên bố sai rằng mọi triển khai JWT đều bắt buộc áp dụng giống nhau.

## 11. Tài liệu thư viện và sản phẩm nằm ở đâu?

Tài liệu thư viện hữu ích để biết API, cấu hình, ngoại lệ và giới hạn triển khai. Nhưng tài liệu đó không tự thay thế giao thức.

Khi đánh giá một thư viện:

- Tìm xem thư viện hỗ trợ RFC/profile nào và phiên bản nào.
- Đọc release notes về thay đổi thuật toán, parser, default và validation.
- Kiểm tra thuật toán mặc định có phù hợp policy không.
- Kiểm tra thư viện tự xác minh issuer/audience/expiration hay chỉ verify chữ ký.
- Kiểm tra cách xử lý unknown `crit`, `kid`, JWK và key rotation.
- Kiểm tra exception mapping để phân biệt invalid credential với dependency/runtime failure.
- Chạy test vector độc lập thay vì chỉ dựa vào unit test của thư viện.

Một thư viện có thể cung cấp hàm tên `verify` nhưng hàm đó chỉ kiểm tra chữ ký. Không suy ra rằng nó đã kiểm tra toàn bộ profile. Đọc mô tả API và xác minh từng bước bằng test.

Nếu tài liệu thư viện có vẻ mâu thuẫn với RFC, xác định thư viện đang triển khai profile nào và version nào; kiểm tra RFC updates, errata và release notes. Nếu thư viện không đáp ứng yêu cầu bắt buộc, cần cấu hình bổ sung, nâng cấp, thay thế hoặc giới hạn cách dùng.

## 12. Kiểm thử conformance và interoperability

Đọc tiêu chuẩn phải dẫn đến các kiểm thử có thể lặp lại. Một bộ test tốt kiểm tra positive cases, negative cases và khác biệt giữa các triển khai.

### Conformance tests

Conformance test xác nhận implementation tuân thủ profile:

- Token đúng serialization, thuật toán, khóa và claims được chấp nhận.
- Sai chữ ký, MAC hoặc authentication tag bị từ chối.
- Issuer/audience/profile không khớp bị từ chối.
- Token hết hạn hoặc chưa đến thời điểm hiệu lực được xử lý theo policy.
- Thuật toán ngoài allowlist bị từ chối.
- Critical header parameter không được hỗ trợ bị xử lý đúng.
- Unknown claims được xử lý theo schema/profile.
- Key không tin cậy hoặc key type không phù hợp bị từ chối.

### Interoperability tests

Interoperability test xác nhận hai triển khai độc lập trao đổi token theo cùng hợp đồng:

- Issuer A phát hành token và consumer B xác minh được.
- Issuer B phát hành token và consumer A xác minh được nếu hai bên cùng hỗ trợ profile.
- JWK/JWKS được serialize và parse nhất quán.
- Thuật toán và key parameters được hai bên hỗ trợ đúng.
- Claims có kiểu và semantics giống nhau.
- Error behavior đủ nhất quán để client xử lý.
- Key rotation không tạo khoảng thời gian consumer hợp lệ bị từ chối ngoài policy.

### Dùng test vectors

Ưu tiên test vector từ RFC, tài liệu profile và bộ kiểm thử chính thức. Bổ sung vector nội bộ cho policy riêng. Với mỗi vector, ghi input, key/algorithm, profile/issuer/audience, kết quả mong đợi, điều khoản RFC hoặc policy làm căn cứ và implementation/version đã chạy test.

Không đưa production token, private key hoặc secret thật vào test fixture, repository hoặc báo cáo kiểm thử.

## 13. Ví dụ quy trình đọc tài liệu cho một tích hợp mới

Giả sử một service cần nhận JWT access token do Authorization Server của đối tác phát hành. Nhóm tích hợp có thể thực hiện:

1. Xác định giao thức và profile: OAuth access token hay một loại JWT khác.
2. Xác định issuer, audience, client, resource và token transport.
3. Đọc RFC 6749, RFC 6750 và profile access token phù hợp.
4. Đọc RFC 7519, RFC 7515, RFC 7517 và RFC 7518 để hiểu token, chữ ký và khóa.
5. Đọc RFC 8725 và RFC 9700 để xác định biện pháp bảo mật.
6. Kiểm tra IANA JOSE registries để xác nhận identifier thuật toán và key type.
7. Lập profile contract gồm required claims, algorithm allowlist, key source, lifetime, error mapping và replay policy.
8. Chọn thư viện có hỗ trợ phù hợp, sau đó kiểm tra từng API theo contract.
9. Tạo test vectors và chạy conformance tests.
10. Trao đổi token thử nghiệm giữa hai triển khai độc lập.
11. Ghi phiên bản tài liệu, RFC updates, policy và kết quả interoperability.
12. Thiết lập quy trình theo dõi thay đổi tiêu chuẩn và dependency khi vận hành.

Đầu ra là một profile contract và bộ test có thể kiểm chứng, không chỉ là đoạn code ký/xác minh token.

## 14. Theo dõi thay đổi tiêu chuẩn theo vòng đời hệ thống

Tiêu chuẩn và khuyến nghị bảo mật có thể được cập nhật sau khi hệ thống triển khai. Cần có cách theo dõi:

- RFC mới có trường Updates/Obsoletes liên quan đến tài liệu đang dùng.
- Errata đã xác minh.
- IANA registry khi có thuật toán hoặc parameter mới.
- BCP mới có thể thay đổi khuyến nghị bảo mật.
- Release notes của thư viện và runtime mật mã.
- Algorithm allowlist và token profiles theo chu kỳ.
- Tác động đến issuer, consumer, partner và token đang lưu hành.
- Test vectors, profile contract và runbook khi thay đổi được chấp thuận.

Không tự động bật thuật toán mới chỉ vì registry có thêm entry. Cần đánh giá mức độ hỗ trợ, tình trạng bảo mật, profile tương thích, khả năng triển khai và yêu cầu migration.

Một thay đổi tài liệu cũng không tự động có nghĩa cần thay đổi production ngay. Xác định yêu cầu là sửa lỗi, khuyến nghị mới, thay đổi tương thích hay breaking impact.

## 15. Các lỗi thường gặp khi đọc và áp dụng tiêu chuẩn

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ đọc RFC 7519 rồi triển khai JWT | Bỏ sót JOSE, profile và JWT BCP | Đọc bộ RFC nền tảng và profile giao thức |
| Coi RFC số lớn hơn luôn thay thế RFC cũ | Dùng sai hoặc bỏ sót yêu cầu vẫn còn hiệu lực | Kiểm tra Updates/Obsoletes và nội dung thay đổi |
| Dùng Internet-Draft như tiêu chuẩn đã xuất bản | Dựa vào nội dung có thể còn thay đổi | Kiểm tra trạng thái trên Datatracker |
| Chỉ đọc Abstract và ví dụ | Bỏ qua normative requirements và security considerations | Đọc conventions, security, IANA và references |
| Coi mọi SHOULD là MUST | Hạn chế tương thích không cần thiết | Đọc đúng normative language và lý do ngoại lệ |
| Coi SHOULD là tùy ý | Bỏ qua khuyến nghị có ý nghĩa bảo mật | Ghi lại lý do khi không tuân theo |
| Coi IANA registration là chứng nhận an toàn | Chấp nhận thuật toán/parameter không phù hợp | Đối chiếu BCP, profile và local policy |
| Dùng `kid` để quyết định schema hoặc trust | Trộn key selection với profile validation | Tách issuer, key, token type và claims schema |
| Dùng JWT generic cho mọi giao thức | Nhầm ID Token, access token và proof JWT | Áp dụng validator riêng cho từng profile |
| Tin tài liệu thư viện hơn hợp đồng giao thức | Phụ thuộc default hoặc behavior riêng | Đối chiếu API với RFC và test vectors |
| Chỉ test trong một thư viện | Không phát hiện khác biệt giữa implementation | Chạy interoperability tests độc lập |
| Không ghi nguồn của policy | Không truy nguyên được lý do khi migration | Lập bảng requirement-to-source |

## 16. Checklist đọc tiêu chuẩn và chọn profile

**Nguồn và trạng thái**

- Xác định nguồn chính thức của tài liệu.
- Kiểm tra RFC status/category và trạng thái Internet-Draft.
- Kiểm tra Updates, Obsoletes, Updated by và Obsoleted by.
- Kiểm tra errata và trạng thái xử lý.
- Đọc normative references và IANA considerations.

**JWT và JOSE**

- Đọc đúng phần JWT, JWS, JWE, JWK và JWA liên quan.
- Xác định serialization và token profile được chấp nhận.
- Tra cứu IANA registry cho algorithm, key type, header parameter và claims.
- Đọc JWT BCP cùng yêu cầu của profile.
- Phân biệt key identifier, issuer, audience, token type và claims schema.

**Hồ sơ giao thức**

- Xác định issuer, consumer, audience, transport và mục đích token.
- Đọc profile OAuth/OIDC/DPoP/mTLS tương ứng.
- Ghi rõ required/optional/forbidden claims và JOSE parameters.
- Xác định error mapping, lifetime, clock skew, revocation và replay requirements.
- Tách protocol requirements, profile requirements và local policy.

**Triển khai và kiểm chứng**

- Đối chiếu API/default của thư viện với hợp đồng đã lập.
- Dùng test vectors và conformance tests.
- Chạy interoperability tests giữa các implementation độc lập.
- Kiểm thử negative cases và unknown/critical parameters.
- Ghi lại nguồn, version tài liệu và quyết định policy.
- Có quy trình theo dõi RFC updates, errata, IANA registries và library releases.

**Ghi nhớ:** JWT là một định dạng trong một hệ sinh thái tiêu chuẩn. Để triển khai liên thông, cần đọc RFC nền tảng về JWT/JOSE, JWT BCP, profile giao thức và IANA registries theo đúng phạm vi. Luôn kiểm tra trạng thái, quan hệ cập nhật, normative language và security considerations. Sau khi đọc, chuyển yêu cầu thành profile contract, test vectors và interoperability tests. Tài liệu thư viện giúp triển khai API; tiêu chuẩn và profile xác định hợp đồng mà các bên cần tuân thủ.

### Tài liệu chuẩn để tra cứu

- **RFC 7515 — JSON Web Signature (JWS):** cấu trúc và quy tắc chữ ký.
- **RFC 7516 — JSON Web Encryption (JWE):** cấu trúc mã hóa JSON.
- **RFC 7517 — JSON Web Key (JWK):** biểu diễn khóa và JWKS.
- **RFC 7518 — JSON Web Algorithms (JWA):** thuật toán và identifier JOSE.
- **RFC 7519 — JSON Web Token (JWT):** claims và serialization JWT.
- **RFC 7797 — JSON Web Signature (JWS) Unencoded Payload Option:** tùy chọn payload không Base64url encode.
- **RFC 8037 — CFRG Elliptic Curve Diffie-Hellman (ECDH) and Signatures in JOSE:** thuật toán/curve bổ sung.
- **RFC 2119 và RFC 8174:** ý nghĩa từ khóa quy phạm.
- **RFC 8725 — JSON Web Token Best Current Practices:** hướng dẫn triển khai JWT an toàn.
- **RFC 6749 và RFC 6750:** OAuth 2.0 framework và Bearer Token Usage.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** metadata/discovery của authorization server.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** mTLS và certificate-bound token.
- **RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens:** profile JWT access token.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** sender-constrained proof.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** hướng dẫn bảo mật OAuth hiện hành.
- **OpenID Connect Core 1.0:** profile xác thực và ID Token do OpenID Foundation công bố.
