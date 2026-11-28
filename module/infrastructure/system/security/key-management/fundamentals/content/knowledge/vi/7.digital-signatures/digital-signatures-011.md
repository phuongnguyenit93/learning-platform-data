# Timestamp của chữ ký — Dấu thời gian và xác minh chữ ký số theo thời điểm

## 1. Timestamp của chữ ký là gì và giải quyết vấn đề nào?

**Timestamp của chữ ký số** là thông tin thời gian được gắn với chữ ký hoặc tài liệu đã ký nhằm hỗ trợ trả lời câu hỏi: **chữ ký hay dữ liệu cần chứng thực đã tồn tại từ khi nào?** Trong một hệ thống có yêu cầu đối soát và lưu trữ lâu dài, câu hỏi này quan trọng gần bằng việc xác minh ai đã ký và nội dung có bị sửa hay không.

Hãy xét một hóa đơn được ký bằng private key của doanh nghiệp vào tháng 1. Đến tháng 6, chứng thư của người ký hết hạn. Người kiểm tra cần biết hóa đơn đã tồn tại và có thể đã được ký **trước thời điểm hết hạn** hay chỉ được tạo ra sau đó. Trường ngày giờ do người ký điền trong PDF hoặc dữ liệu nghiệp vụ có thể bị chỉnh hoặc đặt sai; nó chưa đủ làm bằng chứng thời gian độc lập. Một **dấu thời gian mật mã từ nguồn tin cậy** có thể bổ sung bằng chứng rằng một giá trị hash cụ thể đã tồn tại **không muộn hơn** thời điểm được xác nhận.

Trong chương **Chữ ký số** thuộc mô-đun quản lý khóa mật mã, cần nắm đồng thời ba khía cạnh:

1. **Chữ ký số:** Private signing key ký thông điệp; người kiểm tra dùng public key và thuật toán tương ứng để xác minh.
2. **Chứng cứ thời gian:** Một hệ thống cung cấp dấu thời gian đáng tin, thường là **Time-Stamping Authority (TSA)** theo **RFC 3161**, ký một thông báo có hash và thời gian.
3. **Quản lý khóa/vòng đời:** Signing key, TSA signing key, chứng thư, thông tin thu hồi, thuật toán hash và bằng chứng lưu trữ có thời hạn sử dụng, quyền và rủi ro khác nhau.

> **Điểm cốt lõi:** **Timestamp tự khai báo** không tương đương **trusted timestamp**. Một RFC 3161 timestamp token được kiểm tra hợp lệ có thể chứng minh **một hash tương ứng đã được TSA chứng thực tồn tại trước hoặc tại thời điểm công bố (trong giới hạn độ chính xác và sự tin cậy vào TSA)**; token **không tự chứng minh người ký là ai, giao dịch được phê duyệt hay chữ ký đáp ứng mọi yêu cầu pháp lý**.

### Ví dụ ba câu hỏi khác nhau

- **“Chữ ký này có xác minh được với public key không?”** → Câu hỏi về thuật toán chữ ký và nội dung đã ký.
- **“Ai là chủ sở hữu public key và chứng thư có đáng tin không?”** → Câu hỏi về chứng thư, chuỗi tin cậy, chính sách và trạng thái thu hồi.
- **“Chữ ký này đã tồn tại trước một mốc thời gian không?”** → Câu hỏi về dấu thời gian đáng tin và việc kiểm chứng bằng chứng thời gian.

Một bản PDF có thể trả lời đúng một trong ba câu nhưng vẫn không đáp ứng hai câu còn lại. Vì vậy quá trình xác minh không nên chỉ dựa vào biểu tượng “signed” hay trường ngày giờ hiển thị trên giao diện.

## 2. Phân biệt các loại thời gian trong hệ thống chữ ký

Tên trường có chữ “time” không nói hết giá trị chứng cứ của nó.

| Loại thời gian | Ai đưa ra? | Có ràng buộc mật mã không? | Có thể kết luận gì? |
| --- | --- | --- | --- |
| **Document creation/modification time** | Ứng dụng tạo tài liệu hoặc metadata PDF | Có thể không | Gợi ý thời điểm tạo/sửa, dễ bị thay hoặc sai lệch |
| **Claimed signing time** | Thiết bị/ứng dụng của người ký | Có thể nằm trong phần thuộc tính đã ký | Người ký đã **khai báo** thời gian đó; chưa phải chứng cứ thời gian độc lập |
| **Server received time** | Máy chủ nhận yêu cầu/tài liệu | Thường là log, có thể có kiểm soát bổ sung | Hệ thống đã ghi nhận sự kiện vào thời gian do máy chủ ghi; độ tin cậy phụ thuộc đồng hồ/log |
| **Trusted timestamp (TSA token)** | Đơn vị đóng dấu thời gian đáng tin, với khóa ký riêng | Có, nếu token được xác minh và TSA đáng tin | Hash được token liên kết đã tồn tại **không muộn hơn mốc thời gian của TSA** theo chính sách/độ chính xác |
| **Blockchain anchoring** | Cơ chế ghi nhận vào một sổ cái cụ thể | Có thể có bằng chứng kết hợp hash và giao dịch | Phụ thuộc cơ chế đồng thuận, thời gian block, finality và cách ràng buộc dữ liệu; không tự đồng nghĩa RFC 3161 |
| **NTP-synchronized clock** | Đồng hồ được đồng bộ bằng dịch vụ thời gian | Đồng bộ thời gian có thể được bảo vệ tùy cách triển khai | Giúp vận hành có thời gian ổn định, nhưng **không tự phát hành bằng chứng mật mã độc lập cho tài liệu** |

### Trường `signingTime` đã được ký vẫn có thể không đáng tin

Một số định dạng như **CMS SignedData** có thể mang thuộc tính `signingTime` trong phần thuộc tính được người ký ký số. Khi đó, sửa trường này làm hỏng xác minh chữ ký; tuy nhiên **giá trị ban đầu vẫn do người ký hoặc phần mềm ký lựa chọn**. Người có quyền ký có thể cài đồng hồ sai hoặc cố ý chọn thời gian cũ.

Nghĩa là: chữ ký số có thể bảo vệ **sự toàn vẹn của lời khai thời gian**, nhưng **không xác thực rằng lời khai đó trùng với thời gian thực tế**. Muốn bằng chứng thời gian độc lập, cần nguồn thời gian và cơ chế ký tin cậy bên ngoài người ký.

## 3. RFC 3161 timestamp hoạt động như thế nào?

**RFC 3161** định nghĩa một **Time-Stamp Protocol (TSP)** phổ biến dùng để yêu cầu TSA đóng dấu thời gian cho **giá trị băm (message imprint)**. Dịch vụ TSA không cần nhận toàn bộ tài liệu hay private signing key của khách hàng.

Các thành phần cơ bản:

| Thành phần | Vai trò |
| --- | --- |
| **Client / Time-Stamping Requestor** | Tính hash của dữ liệu cần chứng thực và gửi yêu cầu |
| **Message imprint** | Cặp **thuật toán hash** và **giá trị hash** gửi cho TSA |
| **TSA (Time-Stamping Authority)** | Gắn thời gian từ nguồn đáng tin, phát hành token được ký bằng khóa TSA |
| **TimeStampReq** | Yêu cầu chứa message imprint; có thể có policy, nonce, cờ yêu cầu chứng thư |
| **TimeStampResp** | Phản hồi chứa trạng thái xử lý và **timeStampToken** nếu yêu cầu được chấp nhận |
| **TimeStampToken** | CMS SignedData bao bọc thông tin dấu thời gian và chữ ký của TSA |
| **TSTInfo** | Nội dung token như policy, message imprint, serial number, `genTime`, độ chính xác khi được công bố và nonce nếu có |
| **TSA certificate** | Chứng thư để xác minh chữ ký token và nhận diện quyền sử dụng làm dấu thời gian |

### Luồng phát hành dấu thời gian

~~~mermaid
sequenceDiagram
    participant Signer as Dịch vụ ký
    participant KMS as KMS/HSM ký tài liệu
    participant TSA as TSA đáng tin
    participant Store as Kho tài liệu/bằng chứng
    Signer->>KMS: Sign(tài liệu hoặc digest theo giao thức)
    KMS-->>Signer: Chữ ký số S
    Note over Signer: Tính H(S) nếu timestamp gắn vào chữ ký
    Signer->>TSA: TimeStampReq: hashAlg, H(S), nonce, policy nếu có
    Note over TSA: Kiểm tra yêu cầu, gắn genTime
    TSA-->>Signer: TimeStampResp + token ký bởi TSA
    Note over Signer: Xác minh imprint, chữ ký TSA và chính sách tin cậy
    Signer->>Store: Lưu tài liệu + chữ ký S + timestamp token + metadata
~~~

Trong nhiều định dạng **signature timestamp**, dữ liệu được TSA chứng thực là **giá trị băm của chữ ký số S** sau khi chữ ký đã được tạo, chứ **không nhất thiết là hash của nội dung tài liệu gốc**. Việc liên kết đến tài liệu là qua quan hệ: chữ ký S xác minh cho dữ liệu đã ký, và timestamp token ràng buộc với S. Có các loại **document timestamp** hoặc **archive timestamp** băm những phần khác nhau của gói tài liệu/bằng chứng, tùy định dạng và hồ sơ kỹ thuật.

### Trình tự khái niệm

1. **Tạo chữ ký tài liệu** theo thuật toán và định dạng được phê duyệt.
2. **Chọn đúng byte cần timestamp** theo hồ sơ định dạng: chữ ký, toàn bộ tài liệu ở một phiên bản cụ thể, hoặc gói bằng chứng. Tính hash với thuật toán được hỗ trợ như SHA-256.
3. **Tạo TimeStampReq** gồm thuật toán hash và message imprint, có thể thêm **nonce** ngẫu nhiên để ràng buộc phản hồi với yêu cầu, cùng chính sách TSA mong muốn nếu cần.
4. **TSA xác nhận** yêu cầu, lấy thời gian và phát hành **TSTInfo** được ký bằng private key của TSA; token thường bao gồm thông tin nhận diện chính sách và số serial.
5. **Client kiểm chứng phản hồi**: trạng thái thành công; đúng digest/thuật toán, nonce nếu đã gửi, policy nếu yêu cầu; chữ ký TSA, chứng thư, chuỗi tin cậy và các điều kiện thời gian.
6. **Lưu token nguyên vẹn** cùng chữ ký và tài liệu, đồng thời lưu bằng chứng phục vụ kiểm tra về sau.

**Không tự ghép các trường JSON `hash`, `time`, `signature` rồi gọi đó là RFC 3161.** RFC 3161 sử dụng cấu trúc và quy tắc xác minh cụ thể dựa trên ASN.1/CMS. Cần dùng thư viện hỗ trợ giao thức và hồ sơ định dạng phù hợp.

## 4. Trusted timestamp chứng minh điều gì, và không chứng minh điều gì?

Một token hợp lệ với **message imprint X**, được ký bởi TSA đáng tin và có `genTime = T`, cung cấp chứng cứ rằng **dữ liệu có hash X đã tồn tại hoặc ít nhất TSA đã nhận bằng chứng về X không muộn hơn T**, với giả định TSA vận hành trung thực và thời gian được bảo đảm theo chính sách. Ở mức trực giác: muốn yêu cầu timestamp cho giá trị băm cụ thể, bên yêu cầu phải biết giá trị đó trước khi TSA phát hành token.

Tuy nhiên có một số giới hạn:

1. **Không xác nhận thời điểm ký chính xác.** Timestamp trên chữ ký có thể được yêu cầu **sau** thời điểm tạo chữ ký. Token chỉ hỗ trợ giới hạn trên của thời gian tồn tại chữ ký, không cho biết phút/giây mà người ký thực sự nhấn nút.
2. **Không tự xác minh chữ ký tài liệu.** Nếu chữ ký gốc sai, người ký không được phép, tài liệu bị sửa hoặc khóa ký đã bị chiếm trước đó, TSA vẫn có thể phát hành token cho hash được gửi nếu yêu cầu hợp lệ.
3. **Không tự chứng minh danh tính/ý chí của người ký.** TSA không nhất thiết biết người gửi hash là ai hoặc nội dung tài liệu có hợp pháp hay đã được phê duyệt.
4. **Không mặc nhiên chứng minh chứng thư người ký hợp lệ ở mọi thời điểm.** Phải xây dựng và kiểm tra chuỗi tin cậy cùng bằng chứng trạng thái thu hồi, thời gian và chính sách xác minh riêng.
5. **Không bảo đảm thời gian tuyệt đối chính xác vô hạn.** Timestamp phụ thuộc đồng hồ TSA, khả năng đồng bộ, độ chính xác công bố và mức tin cậy của hạ tầng.
6. **Không là bí mật.** Message imprint và token thường được lưu hoặc trao đổi công khai; hash của dữ liệu nhỏ/dễ đoán có thể tiết lộ thông tin qua thử đoán offline trong một số kịch bản.

Nếu timestamp được gắn vào **hash của chữ ký**, một kẻ tấn công không thể đơn giản thay chữ ký bằng chữ ký khác rồi tái sử dụng token cũ: message imprint sẽ không khớp. Nếu hệ thống chỉ timestamp một chuỗi tùy ý không liên kết được với chữ ký thực, việc “có token hợp lệ” không còn bảo vệ đúng đối tượng cần chứng minh.

## 5. Kiểm tra một timestamp token cần những bước nào?

Đây là phần dễ bị bỏ sót. Một hệ thống có thể nhìn thấy trường `genTime` và hiển thị “đã đóng dấu thời gian”, nhưng chưa kiểm tra token có thật sự được TSA ký và còn đáp ứng chính sách hay không.

### Checklist xác minh token RFC 3161

| Bước | Phải kiểm tra | Nếu bỏ qua sẽ ra sao? |
| --- | --- | --- |
| **1. Giải mã đúng cấu trúc** | TimeStampResp hợp lệ, trạng thái chấp nhận, có token theo quy tắc | Có thể tin dữ liệu lỗi hoặc tự tạo |
| **2. Tính lại imprint** | Hash **đúng byte** được định dạng yêu cầu ràng buộc | Token của đối tượng khác bị ghép nhầm |
| **3. So khớp thuật toán và digest** | Hash algorithm OID và message imprint trong TSTInfo bằng kết quả kỳ vọng | Chấp nhận token cho hash/thuật toán khác |
| **4. Kiểm tra nonce/policy** | Nonce trùng yêu cầu nếu có; policy OID được chấp nhận | Không phát hiện phản hồi nhầm hoặc sai chính sách |
| **5. Kiểm tra chữ ký TSA** | CMS SignedData và signer phù hợp, chữ ký hợp lệ | Kẻ tấn công sửa `genTime` hoặc token |
| **6. Xác thực danh tính TSA** | Chuỗi chứng thư về trust anchor được chấp nhận; mục đích timestamping đúng | Chấp nhận token tự ký hoặc do bên không tin cậy tạo |
| **7. Đánh giá thời gian và chứng thư** | Tính phù hợp của `genTime`, chứng thư TSA tại thời điểm liên quan, trạng thái thu hồi/bằng chứng | Tin token được tạo bằng khóa không hợp lệ theo chính sách |
| **8. Đánh giá thuật toán và chính sách** | Hash, chữ ký, độ dài khóa, TSA policy còn được chấp nhận theo mức an toàn | Tin bằng chứng dựa trên thuật toán đã suy yếu |
| **9. Kết hợp xác minh chữ ký gốc** | Dữ liệu tài liệu, chữ ký, chứng thư người ký và trạng thái thu hồi độc lập | Gắn thời gian cho một chữ ký vốn không hợp lệ |
| **10. Bảo toàn chứng cứ** | Lưu token gốc, chuỗi chứng thư, dữ liệu thu hồi và metadata xác minh | Không kiểm tra độc lập được về sau |

**`genTime` là thời gian do TSA tuyên bố khi phát hành token.** Khi TSTInfo có trường accuracy hoặc ordering, chúng cần được diễn giải theo RFC 3161 và chính sách TSA. Không nên tự so sánh `genTime` với thời gian máy người dùng rồi bỏ qua sai lệch; quy tắc chấp nhận thời gian phải thuộc hồ sơ xác minh được định nghĩa trước.

### Ví dụ mã giả kiểm tra

~~~text
function validateSignatureWithTimestamp(document, signature, token, policy):
    # Chữ ký và đối tượng được ký cần xác minh độc lập.
    signatureOk = verifyDocumentSignature(document, signature, policy)
    if not signatureOk:
        return INVALID_SIGNATURE

    # Các bước dưới đây cần thư viện CMS/RFC 3161 thực sự.
    tstInfo = parseAndVerifyTstInfo(token)
    boundBytes = selectTimestampedBytesAccordingToProfile(signature, document)

    computedImprint = hash(tstInfo.hashAlgorithm, boundBytes)
    require constantTimeEquals(computedImprint, tstInfo.messageImprint)
    require validateTsaSignedDataAndChain(token, policy)
    require validateTsaCertificatePurposeAndTime(token, policy)
    require validateTokenPolicyAndNonceIfApplicable(token, policy)
    require validateAlgorithmsAndRevocationEvidence(token, policy)

    return evaluateSignatureAndEvidenceAtTrustedTime(
        signature, tstInfo.genTime, policy
    )
~~~

Mã giả này **không phải thư viện đã triển khai đầy đủ**, và hàm `evaluateSignatureAndEvidenceAtTrustedTime` không thể chỉ trả `true` khi chứng thư của người ký có `NotBefore ≤ T ≤ NotAfter`: còn phải xét thu hồi, mục đích chứng thư, đường dẫn tin cậy, chính sách, loại chữ ký và bằng chứng lịch sử.

## 6. Chứng thư hết hạn hoặc bị thu hồi: timestamp giúp ra sao?

Một mục đích lớn của dấu thời gian là hỗ trợ xác minh chữ ký **sau khi chứng thư ký đã hết hạn**. Nhưng trường hợp này cần phân biệt cẩn thận giữa **hết hạn**, **thu hồi** và **khóa đã bị lộ**.

### 6.1. Hết hạn chứng thư

Giả sử:

~~~text
01/01/2026: Chứng thư người ký bắt đầu hiệu lực
10/03/2026: Chữ ký được tạo
10/03/2026: TSA timestamp trên chữ ký (đã xác minh)
30/06/2026: Chứng thư người ký hết hạn
01/12/2026: Người nhận xác minh tài liệu
~~~

Nếu dấu thời gian được tin cậy và các điều kiện PKI/chính sách khác được đáp ứng, người nhận **có thể đánh giá chữ ký dựa trên bằng chứng rằng chữ ký đã tồn tại trước khi chứng thư hết hạn**, thay vì chỉ dựa vào thời điểm kiểm tra là tháng 12.

**Không kết luận tự động** rằng chữ ký hợp lệ chỉ vì timestamp nằm trước `NotAfter`. Cần xác minh chữ ký gốc, đúng danh tính, key usage/EKU, chuỗi chứng thư, trạng thái thu hồi liên quan và chính sách xác minh tại thời điểm phù hợp.

### 6.2. Thu hồi chứng thư

**Thu hồi (revocation)** có thể liên quan đến nghi private key bị lộ, thay đổi chủ thể, sai quy trình cấp chứng thư hoặc nguyên nhân khác. Một timestamp sau thời điểm chứng thư bị thu hồi **không cứu được** chữ ký có rủi ro đó. Một timestamp trước thời điểm công bố thu hồi cũng **không tự chứng minh** chữ ký được tạo trước lúc khóa thực sự bị lộ.

Ví dụ:

- Ngày 10/3: Kẻ tấn công có thể đã lấy private key.
- Ngày 11/3: Chữ ký giả mạo được TSA timestamp.
- Ngày 15/3: CA phát hành thông báo thu hồi chứng thư vì lộ khóa.

Token ngày 11/3 có thể là dấu thời gian mật mã hoàn toàn hợp lệ, nhưng **nó chỉ cho biết chữ ký tồn tại vào 11/3**, không chứng minh người ký hợp pháp thực hiện chữ ký hoặc khóa chưa bị lộ.

Khi kiểm tra chữ ký lịch sử, có thể cần **CRL, OCSP response, thời điểm thu hồi, thời điểm phát hiện compromise, bằng chứng bảo quản và chính sách xác minh**. Không dùng duy nhất phép so sánh `T < revocationDate` để tự động khẳng định mọi chữ ký đều đáng tin trong mọi chế độ pháp lý và kỹ thuật.

### 6.3. Chứng thư TSA cũng có vòng đời

Không chỉ private key của người ký, **private TSA signing key và chứng thư TSA** cũng phải có cryptoperiod, mục đích sử dụng, trạng thái, rotation và kiểm toán. Khi chứng thư TSA hết hạn về sau, token lịch sử không nhất thiết mất giá trị ngay nếu tổ chức có cơ chế xác minh dài hạn và bằng chứng phù hợp. Nhưng nếu khóa TSA bị lộ hoặc thuật toán chữ ký/hash của token suy yếu, bằng chứng có thể cần được củng cố bằng cơ chế lưu trữ và **timestamp làm mới** theo chính sách.

## 7. Timestamp, chứng thư, CRL/OCSP và LTV/LTA trong tài liệu dài hạn

Chữ ký được kiểm tra ngay sau khi phát hành có thể dựa vào hệ thống PKI trực tuyến. Khi lưu **5, 10 hoặc 20 năm**, chứng thư hết hạn, URL OCSP không còn truy cập được, CRL không được lưu và thuật toán hiện tại có thể không còn đủ mạnh.

### 7.1. Long-term validation (LTV)

**Long-term validation** nhằm duy trì khả năng kiểm tra chữ ký sau nhiều năm bằng cách **bảo tồn bằng chứng**: chữ ký, timestamp, chứng thư, chuỗi tin cậy, CRL/OCSP hoặc thông tin trạng thái liên quan theo profile. LTV không phải một cờ đơn giản bật trong PDF; nó là tập hợp dữ liệu và quy trình kiểm chứng.

### 7.2. Chữ ký PDF/CMS và profile lưu trữ

| Cơ chế/hồ sơ | Vai trò liên quan đến timestamp | Điều cần nhớ |
| --- | --- | --- |
| **CMS/CAdES** | Có thể chứa signature timestamp và các thuộc tính/bằng chứng xác minh | Phải xem profile CAdES và phần dữ liệu chính xác được timestamp |
| **PAdES** | Chữ ký số và bằng chứng trong PDF, gồm signature/document timestamp tùy mức profile | Một PDF có trường ngày giờ chưa chắc có trusted timestamp |
| **XAdES** | Các thuộc tính chữ ký và bằng chứng trong XML theo profile | Cần canonicalization XML và phép liên kết timestamp đúng |
| **JAR code signing** | Có thể gắn timestamp từ TSA để kiểm tra chữ ký phần mềm về sau | Phải phân biệt việc đọc timestamp với xác minh chuỗi tin cậy của bên ký/TSA |
| **Archive timestamp / LTA** | Bảo vệ một tập hợp bằng chứng đã lưu, có thể cấp timestamp mới trước khi thuật toán cũ suy yếu | Đòi quản trị định kỳ; không phải lưu token một lần rồi bỏ qua vĩnh viễn |

Những tên như **PAdES-B-T, B-LT, B-LTA** chỉ các mức/hồ sơ chức năng liên quan trusted time và bằng chứng lâu dài trong hệ sinh thái PAdES. **B-T** liên quan cung cấp trusted time; **B-LT** bổ sung thông tin cần cho xác minh dài hạn; **B-LTA** hướng tới bảo vệ lâu dài bằng archive timestamp trên dữ liệu/bằng chứng. Khi triển khai phải tham chiếu **phiên bản tiêu chuẩn và chính sách tương ứng**, vì yêu cầu chi tiết phụ thuộc hồ sơ.

### 7.3. Tái timestamp để bảo vệ chứng cứ

Khi mức an toàn của thuật toán hash/chữ ký TSA cũ có nguy cơ không còn đáp ứng thời gian lưu giữ, hệ thống có thể **bổ sung một timestamp mới** trên gói chứng cứ trước khi bằng chứng cũ mất tính tin cậy. Mục tiêu là duy trì chuỗi chứng cứ và tính nguyên vẹn của dữ liệu/bằng chứng theo thời gian.

Việc tạo timestamp mới không “biến” một tài liệu ban đầu không hợp lệ thành hợp lệ. Nó chỉ bổ sung bằng chứng thời gian mới cho một đối tượng/bộ chứng cứ được ràng buộc. Cần lưu các token và dữ liệu gốc để bên xác minh có thể đánh giá từng giai đoạn.

## 8. Vai trò của hàm băm và thuật toán mật mã trong timestamp

TSA thường nhận **message imprint**, tức hash của dữ liệu, thay vì tài liệu nguyên bản. Điều này hạn chế khối lượng dữ liệu trao đổi và giảm nhu cầu tiết lộ nội dung trực tiếp cho TSA.

Tuy nhiên, bằng chứng thời gian chỉ mạnh khi **hash còn đáp ứng yêu cầu kháng va chạm/preimage phù hợp** và chữ ký TSA còn đáng tin.

- **Hash an toàn:** Chọn SHA-256 hoặc thuật toán được chấp nhận theo profile/chính sách. Không dùng MD5/SHA-1 cho quy trình timestamp mới yêu cầu mức kháng va chạm hiện đại.
- **Chữ ký TSA:** Dùng thuật toán chữ ký số được chấp thuận và quản lý private key TSA đúng mục đích, có khả năng chống lạm dụng cấp timestamp.
- **Ràng buộc byte chính xác:** Timestamp của `H(signatureValue)` khác với timestamp của `H(documentBytes)`. Dùng sai byte trong lúc kiểm tra sẽ làm token không còn liên kết đúng.
- **Kiểm soát biểu diễn:** Nếu tài liệu được canonicalize, đóng gói lại hoặc sửa sau khi ký/timestamp, cần tuân theo cấu trúc và quy tắc byte được profile cho phép. Không tùy ý tái tạo chuỗi ký theo cách khác.
- **Algorithm agility:** Lưu thuật toán hash, chữ ký và định dạng token; thiết kế khả năng đổi thuật toán, thay TSA và timestamp lưu trữ về sau.

**Timestamp cũng không phải encryption.** Dù token là thông tin đã ký, dữ liệu tài liệu không được mã hóa chỉ vì có timestamp. Nếu cần bí mật, phải dùng cơ chế như **AES-GCM** và quản lý DEK/KEK trong **envelope encryption** theo mục đích riêng. Hash, signature, timestamp và AEAD bảo vệ những thuộc tính khác nhau.

### Vấn đề riêng tư của message imprint

Digest không phải plaintext, nhưng nếu nội dung nằm trong không gian nhỏ/dễ đoán (ví dụ mã trạng thái “approved/rejected”), bên có digest có thể tự băm các ứng viên để đoán giá trị. Việc gửi một digest cho TSA thường ít lộ thông tin hơn gửi nguyên tài liệu, nhưng không nên gọi digest là “ẩn danh tuyệt đối”. Khi cần, hệ thống phải thiết kế cấu trúc dữ liệu cần timestamp để đáp ứng yêu cầu riêng tư và khả năng xác minh.

## 9. Quản lý khóa ký người dùng và khóa TSA trong KMS/HSM

Có ít nhất **hai vai trò private key** trong quy trình dấu thời gian:

| Khóa | Ai kiểm soát? | Mục đích | Hậu quả khi bị lộ/lạm dụng |
| --- | --- | --- | --- |
| **Private signing key của người ký** | Người ký/tổ chức, theo key owner và key custodian | Ký tài liệu hoặc hash theo thuật toán chữ ký | Giả mạo chữ ký, mạo danh chủ thể ký |
| **Private TSA signing key** | TSA và đơn vị vận hành theo chính sách chuyên biệt | Ký timestamp token, ràng buộc imprint với thời gian TSA | Phát hành hoặc giả mạo dấu thời gian, ảnh hưởng độ tin cậy của token |
| **Public verification key / chứng thư** | Được phân phối cho bên kiểm tra | Xác minh các chữ ký tương ứng | Nếu phân phối sai, bên kiểm tra có thể tin nhầm danh tính |
| **DEK/KEK lưu trữ** | Ứng dụng/KMS và nhóm quản trị | Mã hóa tài liệu/bọc khóa dữ liệu | Lộ nội dung hoặc mất khả năng giải mã, không quyết định tính xác thực thời gian |

**KMS/HSM** hỗ trợ bảo vệ private key và cho phép ký mà không phải xuất vật liệu khóa nếu sản phẩm hỗ trợ. Tuy nhiên, quyền gọi `Sign` bằng TSA key đặc biệt nhạy cảm: nếu kẻ tấn công sử dụng được TSA signing service ngoài chính sách, họ có thể tạo token với thông tin thời gian mà hệ thống TSA chấp nhận. Vì vậy cần kiểm soát **cả cơ chế xác nhận thời gian, nguồn đồng hồ, quyền phát hành và nhật ký sự kiện**, không chỉ đặt private key trong HSM.

### Phân vai

| Vai trò | Quyết định/thao tác điển hình | Kiểm soát quan trọng |
| --- | --- | --- |
| **Key owner của signing key** | Quyết định mục đích, dịch vụ được ký, cryptoperiod và xử lý rủi ro | Không tự cấp mọi quyền quản trị |
| **Key custodian của signing key** | Bảo vệ khóa, triển khai IAM, rotation, backup/hủy theo phê duyệt | Không mặc nhiên được ký nội dung tùy ý |
| **TSA operator/custodian** | Vận hành nguồn thời gian, HSM, dịch vụ timestamp, cấp token và giám sát | Có kiểm soát độc lập với việc đặt thời gian và ký token |
| **Verifier** | Xác minh chữ ký, token, PKI và chính sách thời gian | Trust store và chính sách xác minh không bị sửa tùy tiện |
| **Auditor** | Kiểm tra issuance, quyền, thời gian, sự cố và retention | Được đọc bằng chứng, hạn chế sửa log/chính sách |

Với ứng dụng sử dụng TSA công cộng, **key owner của tài liệu không có quyền quản trị khóa TSA**; tổ chức chỉ lựa chọn nhà cung cấp, trust anchor, profile và chính sách xác minh phù hợp.

### Vòng đời phải được thiết kế trước

1. **Tạo:** Private signing key và TSA key dùng nguồn ngẫu nhiên mật mã, thuật toán được duyệt, môi trường bảo vệ phù hợp.
2. **Cấp phát:** Chỉ các principal cần thiết có quyền ký tài liệu hoặc phát hành token; phân phối public key/chứng thư an toàn.
3. **Sử dụng:** Phê duyệt dữ liệu ký, giới hạn API, bảo vệ dữ liệu đầu vào, chính sách TSA và thời gian; ghi log.
4. **Xoay vòng:** Cập nhật signing key/cert và/hoặc TSA key/cert; đảm bảo bên xác minh vẫn biết cách xử lý token/chữ ký cũ.
5. **Thu hồi/vô hiệu hóa:** Ngừng sử dụng khóa khi nghi lộ hoặc hết trách nhiệm; phân biệt gỡ quyền, thu hồi chứng thư và hủy key material.
6. **Lưu trữ/hủy:** Giữ bằng chứng cần cho xác minh lịch sử; chỉ hủy private key khi hết phụ thuộc và retention; quản lý backup và cơ chế khôi phục có kiểm soát.

## 10. Ví dụ Java: đọc timestamp trong một JAR đã ký

Đối với file JAR, Java cung cấp API để kiểm tra chữ ký của các entry và truy xuất **timestamp liên quan đến người ký**, nếu JAR được ký với TSA phù hợp. Ví dụ minh họa việc đọc thông tin timestamp sau khi JAR được kiểm tra theo cơ chế tích hợp.

**Đầu vào:** Một file JAR đã được ký bằng quy trình `jarsigner` với cấu hình timestamp TSA phù hợp. File JAR không được tự động coi là đáng tin chỉ vì đã có chữ ký hoặc token.

~~~java
import java.io.InputStream;
import java.nio.file.Path;
import java.security.CodeSigner;
import java.security.Timestamp;
import java.util.Enumeration;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public final class JarSignatureTimestampDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: java JarSignatureTimestampDemo <signed.jar>");
        }

        Path file = Path.of(args[0]);
        boolean foundSignedContent = false;

        // verify=true: JarFile kiểm tra chữ ký của các entry khi đọc chúng.
        try (JarFile jar = new JarFile(file.toFile(), true)) {
            Enumeration<JarEntry> entries = jar.entries();

            while (entries.hasMoreElements()) {
                JarEntry entry = entries.nextElement();
                if (entry.isDirectory() || entry.getName().startsWith("META-INF/")) {
                    continue;
                }

                // Phải đọc hết entry để kích hoạt kiểm tra chữ ký.
                try (InputStream stream = jar.getInputStream(entry)) {
                    byte[] buffer = new byte[8192];
                    while (stream.read(buffer) != -1) {
                        // Chỉ tiêu thụ dữ liệu nhằm kích hoạt xác minh entry.
                    }
                }

                CodeSigner[] signers = entry.getCodeSigners();
                if (signers == null || signers.length == 0) {
                    System.out.println("UNSIGNED entry: " + entry.getName());
                    continue;
                }

                foundSignedContent = true;
                for (CodeSigner signer : signers) {
                    Timestamp timestamp = signer.getTimestamp();
                    if (timestamp == null) {
                        System.out.println("SIGNED WITHOUT TSA TIMESTAMP: "
                                + entry.getName());
                    } else {
                        System.out.println("SIGNED AND TIMESTAMPED: "
                                + entry.getName());
                        System.out.println("TSA time: "
                                + timestamp.getTimestamp());
                        System.out.println("TSA certificate path entries: "
                                + timestamp.getSignerCertPath()
                                           .getCertificates().size());
                    }
                }
            }
        } // chữ ký sai có thể phát sinh SecurityException khi đọc entry.

        if (!foundSignedContent) {
            System.out.println("No signed content entries found");
        }
    }
}
~~~

**Giới hạn quan trọng:** Đoạn mã này minh họa **đọc chữ ký và timestamp của JAR**, **không phải hệ thống xác minh trust hoàn chỉnh cho phần mềm production**. Việc có `CodeSigner` hoặc `Timestamp` không tự chứng minh public key/chứng thư của signer/TSA thuộc danh sách tin cậy mà tổ chức chấp nhận; cũng không thay kiểm tra key usage, revocation, policy, thuật toán, quyền phát hành và chính sách toàn bộ artifact. Một file JAR có thể chứa cả nội dung có và không có chữ ký, vì vậy ứng dụng cần chính sách rõ ràng để **từ chối entry không được ký** nếu đó là yêu cầu.

Đối với quy trình ký JAR thực tế, có thể dùng công cụ chuẩn `jarsigner` của JDK và chính sách PKI phù hợp. Đừng tự kết luận toàn bộ JAR đáng tin chỉ từ thông báo `SIGNED AND TIMESTAMPED` của ví dụ này.

### Xử lý timestamp RFC 3161 không thuộc JAR

**Java SE không cung cấp một API cấp cao phổ quát** để xác minh mọi RFC 3161 TimeStampResp/TimeStampToken dùng cho PDF, CMS hoặc tài liệu bất kỳ. Cần thư viện CMS/TSP hỗ trợ cấu trúc ASN.1 và quy trình PKI của hồ sơ đã chọn, chẳng hạn thư viện được tổ chức đánh giá. Tránh tự giải mã ASN.1 một phần rồi bỏ qua xác minh chữ ký TSA.

Trong các thư viện có hỗ trợ RFC 3161, luồng API thường gồm: tạo request từ **message imprint**; gọi TSA; parse response; validate response với request; xác minh token với chứng thư TSA; kiểm tra policy, trust chain, trạng thái chứng thư, thuật toán và lưu token gốc. **Không in nội dung private key hoặc dữ liệu nhạy cảm vào log** khi debug.

## 11. Tình huống thực tế: hóa đơn PDF cần kiểm tra sau nhiều năm

Giả sử doanh nghiệp phát hành hóa đơn điện tử có chữ ký số, cần giữ trong nhiều năm và có thể xuất trình cho đối tác/auditor sau khi chứng thư đã hết hạn.

### Thiết kế tổng quát

~~~mermaid
flowchart TD
    A[Hóa đơn đã chốt nội dung] --> B[Kiểm tra phê duyệt & canonical bytes]
    B --> C[Ký số bằng private signing key trong KMS/HSM]
    C --> D[Signature value S]
    D --> E[Tính message imprint theo PDF/CMS profile]
    E --> F[TSA cấp RFC 3161 token]
    F --> G[Kiểm chứng token, TSA trust và ràng buộc chữ ký]
    G --> H[Lưu PDF chữ ký và timestamp nguyên vẹn]
    H --> I[Lưu chứng thư, CRL/OCSP và bằng chứng LTV]
    I --> J[Verifier đánh giá chữ ký tại thời điểm thích hợp]
    J --> K[Lịch đánh giá lại thuật toán/archival timestamp]
~~~

Luồng này cần thống nhất **profile PDF/PAdES**, phạm vi byte đã ký, vùng byte dự trữ chèn chữ ký/token và cách lưu dữ liệu xác minh. **Không chỉnh PDF tùy tiện sau khi ký** nếu việc chỉnh sửa nằm ngoài những thao tác được định dạng chữ ký cho phép: thay đổi byte có thể làm mất hiệu lực chữ ký hoặc timestamp.

### Vì sao timestamp cần được ràng buộc với chữ ký?

Nếu chỉ ghi vào database:

~~~json
{
  "invoiceId": "INV-2026-001",
  "signedAt": "2026-03-10T08:00:00Z",
  "signed": true
}
~~~

thì đó là **metadata nghiệp vụ**, không tự tạo bằng chứng mật mã đáng tin về thời điểm ký. Ngay cả khi metadata được ứng dụng ký, nó vẫn có thể là thời gian người ký tự khai báo.

Với signature timestamp theo profile phù hợp, ứng dụng gửi **hash của chữ ký S** tới TSA. Bên xác minh đọc lại chữ ký S trong tài liệu, tính lại hash, đối chiếu token và kiểm tra chữ ký TSA. Nhờ vậy token được ràng buộc với chính chữ ký cần xem xét.

### Một bản ghi lưu trữ tối thiểu

| Dữ liệu | Mục đích |
| --- | --- |
| **Document ID / version** | Nhận biết đúng tài liệu cuối cùng |
| **Signed bytes hoặc bản PDF ký nguyên vẹn** | Kiểm tra chữ ký theo đúng phạm vi bytes |
| **Signature algorithm và signer certificate/path** | Xác minh chữ ký và danh tính |
| **TSA token raw + timestamp profile** | Chứng cứ thời gian gắn với chữ ký/dữ liệu |
| **Trust policy/version áp dụng** | Biết tiêu chí chấp nhận trong hệ thống |
| **CRL/OCSP hoặc bằng chứng trạng thái phù hợp** | Đánh giá lịch sử PKI và xác minh dài hạn |
| **Key ID, TSA identity, audit references** | Tra cứu quản lý khóa và điều tra |
| **Retention/revalidation schedule** | Bảo tồn và gia hạn chứng cứ khi cần |

Không lưu **private signing key hoặc private TSA key** trong gói hóa đơn. Những khóa đó được quản trị độc lập trong KMS/HSM hoặc môi trường phù hợp.

## 12. Rủi ro thường gặp khi triển khai timestamp chữ ký

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi `signingTime` của ứng dụng là trusted timestamp | Người ký có thể đặt đồng hồ lùi hoặc khai báo sai | Dùng TSA/protocol và chính sách thời gian đáng tin |
| Chỉ nhìn `genTime` mà không kiểm tra token | Có thể chấp nhận token giả hoặc bị sửa | Xác minh CMS signature, TSA cert/path, imprint và policy |
| Timestamp **document hash** nhưng lại kiểm như **signature hash** | Token không ràng buộc đúng đối tượng | Thực hiện đúng profile PDF/CMS/JAR tương ứng |
| Không so nonce hoặc policy đã yêu cầu | Có thể ghép sai phản hồi hoặc sai chính sách | So request/response, OID và điều kiện giao thức |
| Tin mọi chứng thư TSA có thể ký token | Tin token từ TSA không được tổ chức chấp nhận | Trust anchor, EKU timestamping và policy |
| Chỉ kiểm tra `NotAfter` của signer certificate | Bỏ qua thu hồi, key usage và sự cố lộ khóa | Xác minh PKI/thu hồi và chính sách theo thời điểm |
| Dùng MD5/SHA-1 cho timestamp mới | Tăng nguy cơ collision, giảm độ tin cậy chứng cứ | Chọn SHA-256 trở lên theo profile và chính sách |
| Không lưu CRL/OCSP/bằng chứng xác minh | Không thể kiểm tra độc lập khi dịch vụ PKI ngừng hoạt động | LTV và lưu bằng chứng phù hợp |
| Chỉ lưu token một lần rồi không đánh giá lại | Thuật toán hoặc chứng thư có thể suy yếu trong thời gian lưu lâu | Revalidation, algorithm agility, archival timestamp |
| Lưu token nhưng làm thay đổi signed bytes | Chữ ký hoặc liên kết timestamp bị phá vỡ | Theo đúng quy tắc cập nhật của PDF/CMS/JAR profile |
| Đưa private signing key của ứng dụng vào TSA | Lẫn chức năng, tăng phạm vi phơi nhiễm | Tách khóa ký tài liệu và TSA signing key |
| Giữ TSA key trong HSM nhưng cấp quyền phát hành rộng | Kẻ tấn công có thể lạm dụng dịch vụ phát hành token | IAM, dual control khi phù hợp, audit và bảo vệ nguồn thời gian |
| Xem timestamp như bằng chứng “người ký đã đồng ý” | Kết luận quá phạm vi chứng cứ thời gian | Xác minh danh tính/ủy quyền/phê duyệt nghiệp vụ riêng |

## 13. Kiểm soát vận hành và giám sát cho hệ thống TSA/ứng dụng ký

Một hệ thống phát hành/xác minh timestamp đáng tin cần quy trình vận hành có thể kiểm toán:

1. **Chuẩn hóa thời gian:** Đồng bộ đồng hồ TSA theo nguồn được phê duyệt; giám sát độ lệch, trạng thái nguồn thời gian và độ chính xác. Với SLA cao, xét dự phòng, xác thực nguồn và quy trình khi đồng hồ mất tin cậy.
2. **Tách trách nhiệm:** Quản trị viên hạ tầng, người cấu hình chính sách TSA, người quản lý TSA signing key và auditor có quyền theo nhiệm vụ; tránh một người tự sửa đồng hồ, cấp quyền và ký token mà không có giám sát.
3. **Giới hạn phát hành:** Thực thi policy OID, thuật toán hash được hỗ trợ, giới hạn tải, xác thực khách hàng khi có yêu cầu và chống lạm dụng dịch vụ.
4. **Ghi log có kiểm soát:** Lưu serial của token, key ID/version, thời gian, trạng thái, kết quả kiểm tra, identity/correlation ID phù hợp; không ghi private key hoặc nội dung tài liệu nhạy cảm.
5. **Bảo vệ chứng thư và khóa:** Theo dõi hết hạn, rotation, trạng thái thu hồi và bằng chứng backup/DR của KMS/HSM.
6. **Ứng cứu:** Nếu TSA signing key bị lộ, nguồn thời gian sai nghiêm trọng hoặc phát hiện issuance bất thường, có runbook cô lập, thông báo, đánh giá token bị ảnh hưởng và thay khóa/chứng thư.
7. **Kiểm tra dài hạn:** Diễn tập xác minh offline, khả năng khôi phục chứng cứ và đánh giá lại thuật toán trước khi chúng suy yếu.

### Khi TSA không phản hồi thì có được “ký trước, timestamp sau” không?

Về kỹ thuật, một hệ thống có thể tạo chữ ký trước rồi chờ yêu cầu timestamp sau. Nhưng **token nhận về sau chỉ chứng thực rằng hash/chữ ký đã tồn tại không muộn hơn thời điểm TSA phát hành token**, không làm bằng chứng cho thời điểm cũ do ứng dụng tự ghi. Nếu quy trình nghiệp vụ buộc chữ ký **phải có trusted timestamp ngay khi phát hành**, hệ thống cần từ chối hoàn tất hoặc ghi trạng thái chờ theo chính sách, không hiển thị chữ ký là đã có timestamp hợp lệ.

Khi retry, lưu **đúng signature value** cần timestamp; không tạo lại chữ ký một cách vô tình rồi dùng token cho chữ ký cũ. Nếu request có nonce, phải kiểm tra nonce của response tương ứng. Không trộn token và chữ ký giữa các giao dịch hoặc phiên bản tài liệu.

## 14. Checklist thiết kế trước khi đưa trusted timestamp vào production

1. **Mục tiêu chứng cứ:** Hệ thống cần chứng minh một tài liệu, **chữ ký**, hay cả một gói bằng chứng đã tồn tại trước mốc thời gian nào?
2. **Đúng loại thời gian:** Có phân biệt claimed signing time, log máy chủ và trusted timestamp không? Giao diện có thể hiện mức tin cậy rõ ràng?
3. **Giao thức:** Có dùng RFC 3161 hoặc profile chuẩn được phê duyệt, với thuật toán hash và dữ liệu được timestamp đúng không?
4. **Xác minh:** Có kiểm tra imprint, nonce/policy, chữ ký TSA, chứng thư, EKU, trust anchor, thuật toán và thời gian phù hợp?
5. **Chữ ký gốc:** Có xác minh riêng chữ ký tài liệu, signer certificate chain, key usage, trạng thái thu hồi và quyền ký?
6. **Giới hạn chứng cứ:** Nhóm kỹ thuật có hiểu timestamp chứng minh **mốc tồn tại không muộn hơn T**, không phải chính xác thời điểm nhấn ký hoặc ý chí pháp lý của người ký?
7. **Khóa:** Signing key của người ký và TSA signing key có được tách biệt, bảo vệ trong KMS/HSM thích hợp, quản lý quyền, key state, rotation và hủy?
8. **Kiểm toán:** Có audit nội dung cần thiết như token serial, caller, key ID, thời gian, kết quả phát hành/xác minh mà không lộ private key hoặc plaintext?
9. **Lưu trữ lâu dài:** Có lưu token nguyên vẹn, chứng thư, CRL/OCSP hoặc bằng chứng cần thiết, và kế hoạch LTV/LTA/đánh giá lại thuật toán?
10. **Thay đổi dữ liệu:** Các bước serialize/canonicalize, ký, thêm timestamp và lưu PDF/CMS/JAR có nhất quán về bytes và phiên bản định dạng?
11. **Lỗi và retry:** Khi TSA timeout/từ chối, tài liệu sẽ ở trạng thái gì? Có ngăn ghép sai token, không sửa giả `genTime` và không nhầm thông điệp?
12. **Pháp lý/chính sách:** Có xác định TSA được chấp nhận, mức độ tin cậy, vùng áp dụng và hồ sơ xác minh theo quy định tổ chức/ngành không?

### Ghi nhớ

**Timestamp của chữ ký** bổ sung **chứng cứ thời gian** cho chữ ký số và có thể giúp đánh giá chữ ký lịch sử khi chứng thư đã hết hạn. **TSA RFC 3161** phát hành token được ký trên **message imprint**, với `genTime` và metadata theo chính sách; token chỉ đáng tin khi kiểm tra **đúng byte được ràng buộc, chữ ký TSA, chứng thư, trust chain, policy và bằng chứng PKI liên quan**. Timestamp không thay chữ ký số, không thay việc xác minh danh tính người ký, cũng không tự giải quyết việc chứng thư bị thu hồi hay private key bị lộ. Muốn giữ giá trị chứng cứ lâu dài, hệ thống phải kết hợp **KMS/HSM, phân quyền, kiểm toán, vòng đời khóa, lưu trữ chứng thư/CRL/OCSP và cơ chế LTV/LTA khi cần**, đồng thời duy trì ranh giới rõ ràng giữa **xác thực nội dung, bảo vệ bí mật dữ liệu và chứng thực thời gian**.
