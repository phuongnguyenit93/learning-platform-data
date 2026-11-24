# Thu hồi niềm tin khi issuer hoặc key bị xâm phạm

**Một token có chữ ký hợp lệ chưa chắc còn đáng tin.** Nếu private key dùng để ký JWT bị lộ, kẻ tấn công có thể tạo access token mới với chữ ký vẫn được API chấp nhận. Nếu chính issuer (bên phát hành) bị chiếm quyền, các token được cấp, khóa công khai công bố và cả kết quả kiểm tra trạng thái token cũng có thể bị thao túng. Khi đó, hệ thống cần **thu hồi niềm tin vào key hoặc issuer** ở những nơi kiểm tra token, thay vì chỉ chờ token hết hạn.

Bài học thuộc chương **Mô hình tin cậy** của module SECURITY_TOKEN_SECURITY_FUNDAMENTALS, tập trung vào ranh giới tin cậy trong xác thực, phân quyền và OAuth 2.0/OpenID Connect (OIDC). Ta sẽ phân biệt JWT, opaque token, access token, refresh token, kiểm tra claims, audience, scope, lưu trữ và thu hồi; từ đó xây dựng cách phản ứng khi gốc tin cậy bị phá vỡ.

Sau bài này, bạn có thể giải thích tại sao một token bị đánh cắp khác với một signing key bị đánh cắp; phân biệt thu hồi token, thu hồi key và thu hồi issuer; hiểu rủi ro của JWKS cache; và phác thảo quy trình chặn token giả, khôi phục hệ thống và kiểm chứng ở tất cả Resource Server.

## 1. Chuỗi tin cậy của một token

Trong OAuth 2.0, **Authorization Server** phát hành access token để client gọi **Resource Server** (API). Một JWT access token tự chứa thường được issuer ký bằng private key. Resource Server có thể xác minh chữ ký bằng public key được lấy từ tập khóa tin cậy, thường công bố qua **JWKS (JSON Web Key Set)**. Trong OIDC, client còn phải xác minh **ID token** do OpenID Provider phát hành; ID token không được dùng thay access token để gọi API.

~~~mermaid
flowchart LR
    AS["Authorization Server / Issuer<br/>Ký và cấp token"] -->|Access token| C["Client"]
    C -->|Bearer access token| API["Resource Server"]
    CONF["Trust config:<br/>issuer, audience, algorithm"] --> API
    JWKS["JWKS tin cậy / public key"] -->|Xác minh chữ ký| API
    API -->|Phân quyền tài nguyên| DATA["Dữ liệu nghiệp vụ"]
~~~

Để chấp nhận một JWT, API phải kiểm tra nhiều điều kiện **độc lập**:

1. **Issuer:** claim *iss* trùng issuer mà API đã cấu hình và tin cậy; không tin một issuer chỉ vì token tự khai báo.
2. **Key và chữ ký:** chữ ký hợp lệ với key thuộc issuer đã tin cậy, key chưa bị vô hiệu hóa, thuật toán nằm trong allowlist đã cấu hình.
3. **Đích nhận và thời gian:** claim *aud* đúng Resource Server; kiểm tra *exp*, *nbf* (nếu có), và ràng buộc thời gian khác theo chính sách.
4. **Loại token và quyền:** đúng loại token cho ngữ cảnh gọi API; scope/claims quyền phù hợp thao tác, đồng thời kiểm tra quyền trên đối tượng cụ thể.
5. **Trạng thái thu hồi:** từ chối token, key hoặc issuer bị thu hồi nếu chính sách có cơ chế kiểm tra.

Chữ ký chứng minh rằng token phù hợp với **khóa đang được verifier tin**. Nó **không chứng minh private key chưa bị đánh cắp**. Đó là điểm yếu căn bản khi gốc tin cậy đã bị xâm phạm.

| Thành phần | Nhiệm vụ | Phạm vi niềm tin |
|---|---|---|
| Issuer | Phát hành và định danh nguồn token | Toàn bộ token được chấp nhận từ nguồn này |
| Signing private key | Tạo chữ ký số | Mọi token có thể được ký bằng key đó |
| Public key/JWKS | Cung cấp vật liệu xác minh | Những verifier đã nhận và tin key này |
| Access token | Cho phép client gọi API trong phạm vi được cấp | Một credential/phiên gọi API cụ thể |
| Refresh token | Xin access token mới tại Authorization Server | Khả năng duy trì phiên ủy quyền trong tương lai |

## 2. Token bị lộ khác gì key hoặc issuer bị xâm phạm?

### 2.1. Bị đánh cắp một bearer access token

Kẻ tấn công nắm một **token cụ thể**, có thể phát lại token trong phạm vi *aud*, *scope* và thời hạn còn hiệu lực. Họ thường **không thể tự sửa claims rồi tạo lại chữ ký hợp lệ** nếu không có signing key. Những cách giảm rủi ro gồm bảo vệ chỗ lưu token, HTTPS, token sống ngắn, thu hồi từng token theo trạng thái hoặc mã định danh *jti* khi hệ thống hỗ trợ, và dùng cơ chế ràng buộc bên sở hữu token như DPoP/mTLS cho các trường hợp phù hợp.

### 2.2. Private signing key bị lộ

Kẻ tấn công có thể **tự ký một JWT mới** với danh tính (*sub*), phạm vi quyền (*scope*), audience (*aud*) và thời gian (*exp*) do họ chọn. Token giả có thể vượt qua kiểm tra chữ ký của Resource Server đang tin public key tương ứng. Kiểm tra claims vẫn bắt buộc, nhưng các claims đó có thể đã được **giả mạo bằng key hợp lệ**.

Rút ngắn hạn dùng token **không giải quyết gốc sự cố**: chừng nào key còn được tin, kẻ tấn công có thể liên tục phát hành JWT mới, dù mỗi token chỉ sống vài phút. Do đó cần **chặn key ở tất cả verifier**, kể cả những key đang nằm trong cache.

### 2.3. Issuer hoặc Authorization Server bị chiếm quyền

Sự cố có thể ảnh hưởng cơ chế xác thực, quy trình cấp token, danh tính người dùng, quyền, private key, JWKS và phản hồi introspection. **Tạo một key mới không tự làm issuer an toàn**, bởi hệ thống bị chiếm quyền vẫn có thể thao túng key hoặc phát hành token mới. Nếu chưa thể khoanh vùng và chứng minh phần còn lại sạch, hãy coi **toàn bộ issuer là chưa đáng tin** cho đến khi khôi phục và xác minh lại bằng quy trình độc lập.

### 2.4. Endpoint JWKS hoặc metadata OIDC bị thao túng

Nếu verifier tải public key hoặc issuer metadata từ nguồn do kẻ tấn công kiểm soát, hắn có thể tìm cách đưa key của mình vào tập được tin. Như vậy, có thể tạo token giả **dù private key gốc chưa bị lộ**. Bảo vệ HTTPS, địa chỉ metadata/JWKS đã cấu hình, quyền thay đổi hạ tầng và chuỗi phân phối key là một phần của mô hình tin cậy.

### 2.5. Shared secret khi dùng thuật toán đối xứng

Với cơ chế MAC như HS256, bí mật dùng để **xác minh** cũng đủ để **tạo** MAC. Nếu nhiều API cùng giữ secret, rò rỉ ở một nơi có thể mở rộng phạm vi giả mạo token. Với thuật toán chữ ký bất đối xứng như RS256/PS256/ES256, API thường chỉ cần public key; lộ public key **không đồng nghĩa** với lộ private signing key. Hai loại hệ thống cần kế hoạch ứng cứu và phạm vi khoanh vùng khác nhau.

## 3. Ba cấp độ thu hồi không thể thay thế cho nhau

| Cấp độ | Hành động | Chặn được điều gì? | Chưa giải quyết được điều gì? |
|---|---|---|---|
| **Token/phiên** | Denylist *jti*, vô hiệu hóa session, revoke refresh token/token family | Ngăn dùng một credential hoặc xin thêm token qua phiên đó | Không chặn kẻ tấn công đang giữ private signing key tự ký credential khác |
| **Signing key** | Tất cả Resource Server ngừng tin key bị ảnh hưởng | Chặn JWT giả mạo ký bằng key ấy, bất kể claims hay thời hạn | Issuer đã bị chiếm có thể cấp token qua key khác |
| **Issuer** | Vô hiệu hóa issuer trong trust configuration của các verifier | Từ chối mọi token từ gốc tin cậy nghi bị xâm phạm | Có thể làm gián đoạn đăng nhập và gọi API hợp lệ, cần kế hoạch khôi phục |

Đặc biệt lưu ý: **thu hồi refresh token** ngăn nhiều trường hợp xin access token mới, nhưng không nhất thiết vô hiệu hóa JWT access token đã phát hành. Còn **xóa public key khỏi JWKS** không lập tức vô hiệu hóa JWT được ký bằng key ấy trên các Resource Server đang cache key.

**Key rotation có kế hoạch** khác **key revocation khẩn cấp**. Trong rotation bình thường, key cũ thường được giữ thêm một thời gian để token chưa hết hạn hoạt động. Khi key đã bị lộ, tiếp tục tin key cũ trong khoảng chuyển tiếp có thể cho phép tạo token giả. Phải chủ động chặn key bị lộ, chấp nhận rằng access token hợp lệ ký bằng key đó cũng bị từ chối.

## 4. Runbook ứng cứu khi key hoặc issuer bị xâm phạm

Quy trình dưới đây mang tính kiến trúc. Một tổ chức cần quy định trước người có quyền kích hoạt, các hệ thống liên quan, kênh liên lạc dự phòng và cách kiểm chứng thao tác.

### Bước 1: Phát hiện, cô lập và khoanh phạm vi

Thu thập thời điểm nghi vấn, issuer liên quan, key identifier (*kid*), **dấu vân tay public key**, các API/region/client đang tin issuer, bản ghi phát hành token và thay đổi JWKS hoặc cấu hình. Bảo toàn bằng chứng để điều tra. Ngừng ký bằng key nghi bị lộ, hạn chế quyền truy cập bất thường vào quản lý khóa, cô lập thành phần issuer có dấu hiệu bị kiểm soát.

Chỉ nhìn *kid* là chưa đủ: đây là nhãn chọn khóa do header JWT đưa vào, không phải chứng cứ mật mã tự thân; hai nguồn không được coi cùng key chỉ vì trùng *kid*, và không nên tái sử dụng *kid* cho vật liệu khóa khác.

### Bước 2: Chặn nguồn đã mất niềm tin tại **mọi verifier**

- **Lộ đúng một signing key, issuer còn được kiểm chứng an toàn:** từ chối key bị lộ theo issuer và nhận diện key đáng tin cậy; gỡ khỏi tập key được phép, đồng thời đẩy chính sách chặn có hiệu lực kể cả khi cache vẫn giữ key cũ.
- **Issuer, nguồn JWKS hoặc hạ tầng phát hành bị xâm phạm/chưa rõ phạm vi:** tạm thời từ chối issuer ở Resource Server, API gateway và các client OIDC xác minh ID token liên quan. Đừng tự chuyển sang issuer hay URL khóa được token gợi ý.
- **Verifier chưa nhận cấu hình mới:** coi đây là lỗ hổng còn mở; cần cập nhật toàn bộ instance, service, gateway và vùng triển khai. Với API nhạy cảm, nếu không thể xác minh token an toàn, phải từ chối request hoặc kích hoạt chế độ vận hành hạn chế đã thiết kế từ trước.

~~~mermaid
flowchart TD
    A["Phát hiện nghi issuer / signing key bị lộ"] --> B["Khoanh phạm vi, cô lập và giữ bằng chứng"]
    B --> C{"Chỉ key bị lộ,<br/>issuer đã chứng minh còn sạch?"}
    C -->|Có| D["Chặn key tại tất cả verifier"]
    C -->|Không / chưa rõ| E["Từ chối toàn bộ issuer"]
    D --> F["Xóa cache, đẩy chính sách, kiểm chứng"]
    E --> F
    F --> G["Khôi phục hạ tầng sạch, tạo key mới"]
    G --> H["Cấp token mới và mở lại trust sau xác minh"]
~~~

### Bước 3: Dừng cấp mới và thu hồi credential liên quan

Ngừng sử dụng key bị lộ để phát hành. Thu hồi refresh token, phiên đăng nhập, chuỗi refresh token (*token family*) và ủy quyền còn hiệu lực theo phạm vi ảnh hưởng. Nếu opaque access token được kiểm tra qua introspection, cần đảm bảo nguồn introspection thực sự đã an toàn trước khi tin phản hồi *active*; đồng thời xử lý cache kết quả introspection ở các API.

Việc này giúp giảm rủi ro **cấp tiếp token**, nhưng đối với JWT đã phát hành vẫn cần bước chặn key/issuer ở verifier.

### Bước 4: Tái lập chuỗi tin cậy

Xác định và khắc phục nguyên nhân gốc; tạo signing key mới trong **môi trường đã kiểm chứng sạch**, bảo vệ private key bằng quản lý quyền tối thiểu, kiểm toán và HSM/KMS nếu phù hợp. Rà soát Authorization Server, metadata OIDC, JWKS, hệ thống CI/CD và tài khoản dịch vụ có khả năng thay đổi cấu hình ký.

Nếu issuer bị chiếm quyền, có thể cần tái triển khai hoặc chuyển sang issuer đã được cấu hình lại một cách minh bạch. Chỉ chấp nhận khóa mới sau khi nguồn phát hành và đường phân phối key được xác minh độc lập. Người dùng hoặc client bị ảnh hưởng có thể phải xác thực/ủy quyền lại.

### Bước 5: Kiểm chứng hiệu lực thu hồi

Đánh giá trên mọi Resource Server, gateway và các client OIDC liên quan:

1. **Token test ký bằng key cũ** bị từ chối ngay cả khi một verifier còn giữ JWKS cũ trong cache.
2. Issuer bị chặn bị từ chối trên mọi instance; không tồn tại API đi vòng qua gateway hoặc vùng triển khai chưa cập nhật.
3. Token mới chỉ được chấp nhận khi chữ ký, issuer, audience, thời gian và quyền đều đúng.
4. Refresh token/phiên đã thu hồi không xin được token mới; chính sách refresh token rotation phát hiện sử dụng lại khi áp dụng.
5. Giám sát cho thấy tất cả verifier đã nhận cùng phiên bản chính sách và không còn chấp nhận key đã bị thu hồi.

Nên thực hiện các negative test bằng khóa/token **kiểm thử được kiểm soát**, trong môi trường và quy trình được ủy quyền; không dùng token giả để dò hệ thống production.

## 5. Vì sao JWKS cache khiến thu hồi key khó hơn?

Một JWT tự chứa có thể được xác minh tại chỗ. Resource Server thường cache JWKS để tránh gọi Authorization Server cho mỗi request. Cache có thể nằm trong thư viện JWT, API gateway, proxy, sidecar hoặc nhiều instance ở các vùng khác nhau.

Hãy xét một tình huống:

1. 09:00 — Kẻ tấn công có được private key **K1**.
2. 09:05 — Issuer gỡ public key K1 khỏi JWKS và bắt đầu dùng key **K2**.
3. 09:06 — Orders API vẫn có K1 trong cache, vẫn xác minh được JWT do kẻ tấn công ký bằng K1.
4. 09:10 — Quy tắc chặn K1 được đẩy đến Orders API, Payments API và gateway, ưu tiên cao hơn JWKS cache; token K1 mới bị từ chối ở mọi nơi.

Các mốc thời gian chỉ là **ví dụ minh họa**, không phải SLA hay thời gian cập nhật chuẩn. Điểm quan trọng là **công bố JWKS mới khác với phân phối và thực thi lệnh thu hồi**.

Các nguyên tắc kiểm tra khóa cần được giữ chặt:

- Chỉ tìm key trong **tập khóa của issuer đã được cấu hình tin cậy**, qua HTTPS và metadata/JWKS đã xác thực.
- Áp dụng allowlist thuật toán ở server; không tin header *alg* chỉ vì token tự công bố giá trị đó.
- Không tự tải key từ URL *jku*, *x5u* hoặc trường tương tự do token cung cấp rồi coi là đáng tin.
- Gắn key với issuer, môi trường và chính sách xác minh; không dùng một key từ issuer khác chỉ vì trùng *kid*.
- Khi không có key đủ tin cậy để xác minh chữ ký, **từ chối token**. Không “fail open” bằng cách bỏ qua chữ ký hay issuer.
- Dùng cơ chế làm mới/xóa cache khẩn cấp, kèm phân phối quy tắc chặn key/issuer vượt lên trên dữ liệu cache.

Trong sự cố mạng thông thường, một số hệ thống có thể dùng key đã cache theo chính sách sẵn có. Nhưng **khi đã xác nhận key/issuer bị xâm phạm**, cache không phải lý do để tiếp tục tin vào nguồn đã bị thu hồi.

## 6. Ảnh hưởng lên JWT, opaque token, access token và refresh token

| Loại token | Cơ chế xác minh thường gặp | Ứng phó khi gốc tin cậy bị xâm phạm |
|---|---|---|
| **JWT access token** | API kiểm chữ ký, issuer, audience, thời hạn và scope tại chỗ | Chặn key hoặc issuer ở tất cả API; gỡ cache cũ; cấp lại token sau khôi phục |
| **Opaque access token** | API introspection hoặc tra trạng thái tại Authorization Server | Vô hiệu hóa trạng thái token, kiểm chứng introspection còn đáng tin, xử lý cache introspection |
| **Refresh token** | Authorization Server kiểm tra khi client đổi token | Revoke token/token family, theo dõi rotation và replay, buộc ủy quyền lại khi cần |
| **OIDC ID token** | Client/Relying Party xác minh token do OpenID Provider cấp | Chặn issuer/key tại nơi xác minh ID token và phục hồi xác thực danh tính |

**JWT** là định dạng token; **access token** là mục đích dùng để truy cập API; **refresh token** có mục đích xin token mới. Không phải mọi access token đều là JWT, và không phải JWT nào cũng là access token. Không dùng ID token để thay access token ở Resource Server.

Thu hồi opaque token có thể hiệu quả sớm hơn khi Resource Server introspection mỗi request, nhưng nếu Authorization Server bị chiếm quyền, phản hồi introspection có thể sai. Cache kết quả introspection cũng tạo độ trễ. Do đó, **tin cậy nguồn xác minh** quan trọng với cả token tự chứa lẫn token tham chiếu.

## 7. Ví dụ toàn bộ: issuer đơn hàng bị sự cố

Giả sử issuer **https://login.example.org** cấp JWT cho hai API: **orders-api** và **payments-api**. Mỗi API chỉ chấp nhận token có issuer khớp cấu hình và audience đúng dịch vụ. Ban đầu cả hai xác minh chữ ký bằng public key **K1**.

### Tình huống A: Chỉ private key K1 bị lộ

Issuer được xác minh vẫn hoạt động an toàn và đã ngừng ký bằng K1. Nhóm ứng cứu tạo **K2** trong môi trường sạch, cập nhật nguồn khóa rồi **đẩy lệnh từ chối K1 đến tất cả API và gateway**, kể cả những nơi còn cache public key K1. Người dùng/client nhận token K2 mới sau quy trình xác thực lại hoặc làm mới hợp lệ; các token K1 cũ bị từ chối.

Quy tắc xác minh ở API cần thể hiện ý tưởng sau:

~~~text
Nhận access token
  -> tìm issuer mong đợi từ cấu hình API
  -> nếu issuer đang bị chặn: reject
  -> chọn key chỉ từ tập khóa tin cậy của issuer
  -> nếu key bị thu hồi hoặc thuật toán không được phép: reject
  -> xác minh chữ ký (không tin claims trước bước này)
  -> kiểm tra iss, aud, exp, nbf nếu có và loại token
  -> kiểm tra scope và quyền trên tài nguyên cụ thể
  -> chỉ khi mọi bước đạt: allow
~~~

Đây là **pseudocode kiến trúc**; trong ứng dụng Java hoặc hệ thống khác, nên dùng thư viện JWT/OAuth được duy trì, cấu hình thuật toán/issuer/audience chính xác, không tự viết thuật toán chữ ký hay parser.

### Tình huống B: Cả issuer bị chiếm quyền

Dù issuer vừa công bố K2, không có cơ sở kết luận key này an toàn: kẻ tấn công có thể tự tạo K2, thay metadata/JWKS hoặc cấp quyền giả. Cả Orders API và Payments API phải tạm **từ chối issuer** đến khi hạ tầng phát hành, khóa, cấu hình và dữ liệu xác thực được khôi phục, kiểm chứng độc lập. Việc mở lại niềm tin phải dựa trên quy trình xác nhận an toàn, không chỉ dựa vào việc “chữ ký K2 hợp lệ”.

## 8. Chuẩn bị trước sự cố và đo hiệu quả ứng cứu

Để phản ứng nhanh, cần có sẵn bản đồ **ai đang tin issuer nào, qua key nào và cache ở đâu**. Runbook nên trả lời được những câu hỏi:

| Câu hỏi | Năng lực cần chuẩn bị |
|---|---|
| Ai được phép chặn issuer/key? | Phân quyền ứng cứu, phê duyệt và kênh liên lạc độc lập với issuer |
| Thành phần nào xác minh token? | Danh sách Resource Server, gateway, OIDC client, vùng triển khai, thư viện, proxy |
| Có thể ngừng tin K1 tức thì không? | Policy denylist key/issuer đẩy khẩn cấp và ưu tiên cao hơn cache |
| Key mới có đáng tin không? | Quy trình khôi phục môi trường sạch, quản lý private key và kiểm tra JWKS |
| Token đang lưu trên client xử lý thế nào? | Thu hồi refresh token/phiên, quy trình đăng nhập lại và cấp access token mới |
| Làm sao biết đã chặn hết? | Quan sát phiên bản trust policy mỗi instance, negative test key cũ, alert chấp nhận key bị thu hồi |
| JWKS không truy cập được thì sao? | Quy tắc từ chối token không xác minh được và phương án vận hành giới hạn |

Theo dõi thay đổi JWKS bất thường, truy cập bất thường vào dịch vụ ký, sự kiện cấp token với issuer/audience/scope lạ, gia tăng lỗi xác minh, các API còn dùng phiên bản policy cũ và lưu lượng từ key đã thu hồi. Log phải đủ cho điều tra **nhưng không ghi nguyên bearer token, refresh token hay private key**.

Thực hành phòng ngừa gồm quản lý khóa tập trung, quyền tối thiểu, HSM/KMS khi phù hợp, tách môi trường, kiểm soát thay đổi JWKS, hạn dùng access token ngắn theo rủi ro, bảo vệ refresh token, detection cho refresh token reuse và diễn tập rotation/thu hồi. Mục tiêu là rút ngắn thời gian từ lúc phát hiện đến lúc **mọi verifier thực sự ngừng tin**.

## 9. Câu hỏi tự kiểm tra

1. **Một JWT ký đúng bằng K1 vẫn có thể là giả mạo không?** Có, nếu private key K1 đã bị lộ. Chữ ký chỉ chứng minh khớp key, không chứng minh người ký là issuer hợp pháp.
2. **Xóa K1 khỏi JWKS đã đủ chưa?** Chưa. Các verifier có thể cache hoặc giữ K1 trong cấu hình tĩnh, nên cần chặn key và xác minh đã cập nhật toàn bộ.
3. **Thu hồi refresh token làm access token JWT cũ hết hiệu lực ngay không?** Không nhất thiết. API chỉ tự xác minh chữ ký và thời hạn có thể vẫn chấp nhận nó nếu không có kiểm tra thu hồi bổ sung.
4. **Khi issuer bị chiếm quyền, tạo K2 mới có giúp an toàn ngay không?** Không. Cần kiểm chứng cả môi trường phát hành, chuỗi phân phối key và cấu hình tin cậy; nếu chưa chắc chắn, vẫn phải chặn issuer.
5. **Vì sao phải kiểm tra audience và scope sau khi khôi phục?** Vì chữ ký hợp lệ không mặc nhiên cấp quyền cho mọi API hoặc tài nguyên. Xác minh nguồn token và phân quyền là hai ranh giới khác nhau.

**Ghi nhớ:** Thu hồi **một token**, thu hồi **signing key** và thu hồi **issuer** là ba hành động có phạm vi khác nhau. Khi key hoặc issuer bị xâm phạm, điều quan trọng nhất là bảo đảm **mọi nơi xác minh token đều ngừng tin nguồn bị ảnh hưởng**, ngay cả khi JWT chưa hết hạn và chữ ký vẫn hợp lệ. Chỉ phát hành token thay thế và khôi phục dịch vụ sau khi đã xây dựng, phân phối và kiểm chứng chuỗi tin cậy mới.
