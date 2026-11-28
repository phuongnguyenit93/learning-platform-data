# Managed identity

## 1. Mục tiêu và phạm vi

Trong một hệ thống có nhiều dịch vụ, ứng dụng thường cần gọi cơ sở dữ liệu, đọc cấu hình, lấy bí mật từ vault hoặc thực hiện tác vụ quản trị hạ tầng. Nếu mỗi ứng dụng giữ một mật khẩu quản trị dài hạn, tổ chức phải giải quyết đồng thời nhiều bài toán: phân phối bí mật, lưu trữ, luân chuyển, thu hồi, kiểm kê và truy vết người hoặc tiến trình đã sử dụng.

Managed identity là một cách giảm phần việc quản lý credential trực tiếp của ứng dụng. Nền tảng cung cấp một danh tính cho workload và cơ chế lấy token tương ứng. Đội vận hành vẫn phải quyết định **danh tính đó được làm gì, trên tài nguyên nào, ai có thể sử dụng nó và khi nào quyền phải kết thúc**.

Bài học đặt managed identity trong quản lý tài khoản dịch vụ và quản lý truy cập đặc quyền (PAM). Sau bài này, bạn có thể:

- Phân biệt danh tính, credential, token, quyền và tài nguyên chạy ứng dụng.
- Chọn ranh giới danh tính phù hợp với workload và môi trường.
- Phân tích nguy cơ từ quyền gắn danh tính và quyền sửa mã ứng dụng.
- Thiết kế quyền tối thiểu, kiểm kê, giám sát và quy trình thu hồi.
- Lập kế hoạch chuyển từ credential dài hạn sang managed identity.
- Kiểm chứng việc truy cập thành công lẫn việc truy cập không được phép bị từ chối.

Các ví dụ dùng Azure để minh họa thuật ngữ system-assigned và user-assigned. Những mẫu kiểm soát, hồ sơ và giả mã trong bài là đề xuất thiết kế cho tình huống học tập; cần ánh xạ sang dịch vụ và cơ chế phân quyền thực tế trước khi triển khai.

## 2. Hiểu đúng mô hình danh tính

### 2.1. Danh tính không phải mật khẩu

Cần phân biệt năm thành phần:

| Thành phần | Câu hỏi nó trả lời | Ví dụ trong một thiết kế |
|---|---|---|
| Workload | Phần mềm nào đang thực hiện công việc? | Dịch vụ xử lý hóa đơn |
| Danh tính | Hệ thống nhận diện chủ thể gọi là ai? | Danh tính của dịch vụ xử lý hóa đơn production |
| Credential nền | Chủ thể chứng minh danh tính bằng cơ chế nào? | Vật liệu xác thực do nền tảng quản lý |
| Access token | Bằng chứng truy cập nào được gửi trong một lần gọi? | Token có thời hạn dành cho dịch vụ đích |
| Quyền | Chủ thể được phép thực hiện việc gì? | Đọc một tập dữ liệu xác định |

Trong Azure, managed identity cho phép ứng dụng lấy token Microsoft Entra mà không tự quản lý credential nền. Dịch vụ đích xác thực token và đánh giá quyền truy cập; bật danh tính chưa tự cấp quyền với dữ liệu. [Microsoft Learn: Securing managed identities](https://learn.microsoft.com/en-us/entra/architecture/service-accounts-managed-identities).

Ví dụ, dịch vụ xử lý hóa đơn có thể lấy được token hợp lệ nhưng vẫn bị từ chối đọc kho báo cáo vì chưa có quyền. Ngược lại, một token đúng danh tính và có quyền quá rộng có thể cho phép nhiều thao tác hơn nhu cầu nghiệp vụ.

**Không phải tự lưu mật khẩu** và **không còn rủi ro credential** là hai kết luận khác nhau. Access token vẫn cần được bảo vệ trong bộ nhớ, log, trace và kênh truyền.

### 2.2. Managed identity liên quan thế nào đến service account?

Service account là cách gọi theo mục đích sử dụng: một danh tính phục vụ phần mềm hoặc tác vụ tự động. Managed identity là một cách triển khai danh tính workload với sự hỗ trợ của nền tảng.

Một service account có thể sử dụng mật khẩu, chứng thư, cơ chế liên kết danh tính hoặc cơ chế được nền tảng quản lý. Vì vậy, không nên lập danh mục như thể mọi service account đều là tài khoản người dùng có mật khẩu.

Trong hồ sơ PAM, hãy ghi mục đích và đặc quyền thực tế. Một managed identity chỉ đọc cấu hình ít nhạy cảm khác đáng kể với một managed identity có thể thay đổi chính sách truy cập của toàn bộ môi trường.

## 3. Luồng truy cập cơ bản

Xét dịch vụ tạo báo cáo chạy trên một tài nguyên tính toán và cần đọc dữ liệu ở một dịch vụ lưu trữ.

~~~mermaid
sequenceDiagram
    participant W as Workload báo cáo
    participant P as Cơ chế danh tính nền tảng
    participant I as Bên phát hành token
    participant D as Dịch vụ dữ liệu
    W->>P: Yêu cầu token cho đích đã cấu hình
    P->>I: Xác thực danh tính theo cơ chế nền tảng
    I-->>P: Access token có thời hạn
    P-->>W: Token hoặc credential abstraction
    W->>D: Gọi thao tác đọc với token
    D->>D: Kiểm tra token và đánh giá quyền
    D-->>W: Kết quả hoặc từ chối
~~~

Đây là sơ đồ khái niệm. Endpoint, SDK, cách xác định tài nguyên đích và cơ chế cache phụ thuộc môi trường chạy.

Luồng này có hai mối quan hệ cần cấu hình riêng:

1. **Quan hệ sử dụng danh tính:** workload nào được phép yêu cầu token dưới danh tính nào.
2. **Quan hệ cấp quyền:** danh tính đó được phép thao tác trên tài nguyên đích nào.

Nếu chỉ kiểm tra quan hệ thứ hai, tổ chức có thể bỏ sót một workload khác vừa được gắn cùng danh tính. Nếu chỉ kiểm tra quan hệ thứ nhất, tổ chức có thể không phát hiện quyền của danh tính đã được mở rộng.

### Audience và phạm vi quyền

Token cần dành cho đúng dịch vụ đích. Không nên thiết kế ứng dụng nhận một URL tùy ý từ người dùng rồi gửi kèm token đặc quyền đến URL đó.

Trong ví dụ học tập, dịch vụ báo cáo có danh sách đích được cấu hình trước. Người dùng có thể chọn kỳ báo cáo, nhưng không được thay đổi endpoint để biến ứng dụng thành công cụ gửi token ra ngoài.

Cấu hình đích, cấu hình danh tính và dữ liệu yêu cầu của người dùng cần có ranh giới rõ ràng.

## 4. Hai kiểu managed identity trong Azure

Azure phân biệt hai kiểu:

| Thuộc tính | System-assigned | User-assigned |
|---|---|---|
| Vòng đời | Gắn với tài nguyên nguồn; bị xóa cùng tài nguyên đó | Độc lập với tài nguyên sử dụng |
| Gắn với tài nguyên | Dành cho một tài nguyên | Có thể gắn cho nhiều tài nguyên được hỗ trợ |
| Khởi tạo | Khi bật trên tài nguyên nguồn | Tạo danh tính riêng rồi gắn |
| Điều phải quản trị | Quan hệ giữa tài nguyên nguồn và quyền đích | Cả vòng đời danh tính và danh sách tài nguyên dùng nó |

Đặc điểm vòng đời và khả năng chia sẻ trên là hành vi của Azure, không phải quy tắc chung cho mọi hệ thống danh tính workload. [Microsoft Learn: Managed identity types](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview#managed-identity-types).

### 4.1. Chọn dựa trên ranh giới tin cậy

Giả sử có ba thành phần:

- API công khai tiếp nhận yêu cầu.
- Worker nền tổng hợp dữ liệu.
- Job quản trị thay đổi cấu trúc lưu trữ.

Không nên gắn chung một danh tính đặc quyền chỉ vì chúng cùng thuộc dự án. API công khai cần quyền khác job quản trị. Một lỗi trong API có thể trở thành đường sử dụng đặc quyền của job nếu hai bên dùng chung danh tính.

Một phương án minh họa:

| Thành phần | Danh tính đề xuất | Quyền nghiệp vụ |
|---|---|---|
| API production | `mi-orders-api-prod` | Đọc cấu hình và ghi yêu cầu vào hàng đợi của nó |
| Worker production | `mi-orders-worker-prod` | Đọc hàng đợi, cập nhật dữ liệu xử lý |
| Job quản trị | `mi-orders-maintenance-prod` | Chỉ các thao tác quản trị đã được phê duyệt |
| API staging | `mi-orders-api-stg` | Chỉ tài nguyên staging |

Tên trong ví dụ là nhãn dễ đọc, không phải bằng chứng nhận dạng. Hồ sơ kiểm kê cần định danh ổn định của principal và tài nguyên để phân biệt các đối tượng trùng tên.

### 4.2. Khi dùng chung danh tính có thể chấp nhận được?

Nhiều replica của cùng một workload có thể có cùng nhu cầu quyền. Dùng chung danh tính có thể phù hợp nếu chúng cùng chủ sở hữu, cùng môi trường, cùng mức tin cậy và cùng vòng đời cấp quyền.

Đổi lại, cần trả lời:

- Có phân biệt được replica nào gây ra một thao tác không?
- Có thể cô lập một replica mà không làm mất truy cập của toàn bộ dịch vụ không?
- Quyền mới thêm cho danh tính có hợp lý với tất cả replica không?
- Có workload khác âm thầm tham gia nhóm sử dụng không?

Khi các câu trả lời không rõ, sự đơn giản của số lượng danh tính có thể đổi thành khó khăn khi điều tra và thu hồi.

## 5. Ranh giới bảo mật nằm ở đâu?

Một nhầm lẫn nguy hiểm là coi managed identity như danh tính riêng của từng tiến trình trên cùng một máy.

Với Azure VM, Microsoft xác định ranh giới của managed identity là tài nguyên VM; mã chạy trên VM có thể gọi endpoint danh tính để yêu cầu token. Không nên xem các tiến trình trên cùng VM là đã được cách ly danh tính chỉ vì chúng là các ứng dụng khác nhau. [Microsoft Learn: Security boundary of managed identities](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/managed-identities-faq#what-is-the-security-boundary-of-managed-identities-for-azure-resources).

Từ đặc điểm này, có thể rút ra một quyết định thiết kế: không đặt một ứng dụng ít tin cậy cạnh một tác vụ có danh tính quản trị mạnh rồi kỳ vọng chỉ tác vụ quản trị mới dùng được danh tính. Cần chọn ranh giới chạy ứng dụng và cơ chế danh tính thực sự hỗ trợ mức cách ly mong muốn.

### 5.1. Ba đường có thể dẫn đến sử dụng đặc quyền

Xét một danh tính có thể sửa cấu hình nhạy cảm:

~~~text
Quyền cấp quyền cho danh tính
    -> Làm danh tính mạnh hơn

Quyền gắn danh tính vào một tài nguyên
    + Quyền chạy mã trên tài nguyên đó
    -> Có thể sử dụng quyền đã có của danh tính

Quyền sửa mã hoặc điều khiển workload đang mang danh tính
    -> Có thể hành động dưới danh tính của workload
~~~

Đây là mô hình phân tích nguy cơ, không phải kết luận rằng mọi quyền sửa cấu hình đều đủ để chiếm danh tính. Cần kiểm tra thao tác thực tế mà quyền đó cho phép: sửa image, thay startup command, thực thi từ xa, sửa pipeline, thay plugin hoặc nhập mã.

**Quyền triển khai mã vào workload đặc quyền phải được xem xét như một đường truy cập đặc quyền.** Việc người triển khai không nhìn thấy credential nền không loại bỏ đường sử dụng danh tính.

### 5.2. Bảo vệ cơ chế lấy token

Đội phát triển nên kiểm soát các chức năng có thể gửi yêu cầu mạng hoặc thực thi mã thay người dùng. Một lỗ hổng kiểu SSRF, một plugin không tin cậy hoặc một công cụ chẩn đoán chạy lệnh tùy ý có thể làm lộ đường truy cập danh tính tùy nền tảng.

Các biện pháp thiết kế gồm:

- Không cho dữ liệu người dùng tự do quyết định đích yêu cầu nội bộ.
- Hạn chế và giám sát chức năng thực thi mã hoặc lệnh quản trị.
- Giảm số ứng dụng có mức tin cậy khác nhau trên cùng ranh giới chạy.
- Giới hạn quyền của danh tính ngay cả khi workload bị kiểm soát.
- Kiểm chứng các biện pháp mạng và endpoint theo nền tảng; không coi một header là lớp cách ly ứng dụng hoàn chỉnh.

## 6. Thiết kế least privilege cho managed identity

### 6.1. Bắt đầu từ tác vụ, không bắt đầu từ vai trò quản trị

Trước khi cấp quyền, viết yêu cầu bằng động từ nghiệp vụ:

> Worker cần đọc thông điệp từ hàng đợi A và ghi kết quả vào vùng dữ liệu B. Worker không cần xóa vùng dữ liệu, cấp quyền cho danh tính khác hoặc quản trị hạ tầng.

Sau đó ánh xạ từng tác vụ sang cơ chế phân quyền thực tế.

| Nhu cầu | Phạm vi mong muốn | Kiểm tra ngoài phạm vi |
|---|---|---|
| Đọc cấu hình ứng dụng | Chỉ tập cấu hình của ứng dụng | Không sửa hoặc đọc cấu hình dịch vụ khác |
| Ghi kết quả xử lý | Chỉ vùng dữ liệu đầu ra | Không thay đổi chính sách truy cập |
| Lấy một bí mật còn cần thiết | Chỉ bí mật hoặc ranh giới vault phù hợp | Không liệt kê hay đọc bí mật ngoài nhu cầu |
| Thực hiện bảo trì | Chỉ thao tác quản trị được duyệt | Không tự cấp thêm quyền hoặc mở rộng tài nguyên |

Nếu sản phẩm không hỗ trợ mức phân quyền chi tiết mong muốn, cần thay đổi ranh giới tài nguyên hoặc ghi nhận ngoại lệ. Không mô tả một quyền rộng là “tối thiểu” chỉ vì ứng dụng hiện chỉ gọi một thao tác.

### 6.2. Kiểm tra cả quyền trực tiếp và quyền gián tiếp

Quyền hiệu lực có thể đến từ nhiều đường:

~~~text
Quyền trực tiếp tại tài nguyên
+ Quyền kế thừa từ phạm vi cha
+ Quyền qua nhóm hoặc quan hệ phân quyền khác
+ Khả năng lấy một credential khác
+ Khả năng thay đổi chủ thể có quyền cao hơn
= Những đường truy cập cần đánh giá
~~~

Dòng cuối là tập đường cần phân tích, không phải phép cộng số học của các role.

Ví dụ, danh tính không có quyền đọc dữ liệu trực tiếp nhưng có thể lấy một khóa cho phép đọc toàn bộ dữ liệu thì vẫn có đường truy cập đáng kể. Tương tự, danh tính chỉ đọc vault có thể rất mạnh nếu vault chứa credential quản trị của nhiều hệ thống.

Cần đánh giá kết quả cuối cùng của chuỗi truy cập, không chỉ tên vai trò ban đầu.

### 6.3. Phân biệt quản trị hạ tầng và truy cập dữ liệu

Trong thiết kế, hãy tách các câu hỏi:

- Có thể tạo, sửa hoặc xóa tài nguyên không?
- Có thể đọc hoặc ghi dữ liệu bên trong không?
- Có thể thay đổi người được truy cập không?
- Có thể lấy một bí mật hoặc khóa làm thay đổi đường truy cập không?

Không suy ra quyền dữ liệu chỉ từ việc có thể nhìn thấy tài nguyên trên cổng quản trị. Cũng không suy ra rằng quyền quản trị cấu hình là vô hại với dữ liệu. Các đường bắc cầu phải được kiểm chứng trên đúng dịch vụ.

## 7. Managed identity không tự tạo JIT hoặc JEA

Token có thời hạn không có nghĩa quyền đã được cấp theo Just-in-Time.

Nếu một workload chạy liên tục, mang danh tính có quyền quản trị thường trực và có thể lấy token mới bất cứ lúc nào, thì thời hạn token không biến quyền thường trực đó thành quyền tạm thời.

Tách ba loại thời gian:

| Loại thời gian | Ý nghĩa |
|---|---|
| Thời hạn token | Token cụ thể có thể được dùng trong bao lâu theo cơ chế đích |
| Thời gian workload được dùng danh tính | Khoảng thời gian quan hệ gắn hoặc cơ chế tin cậy cho phép |
| Thời gian quyền có hiệu lực | Khoảng thời gian principal được phép thực hiện thao tác |

Muốn kiểm soát JIT cho tác vụ bảo trì, có thể thiết kế một job riêng, yêu cầu thay đổi được duyệt, danh tính riêng và quyền có chu kỳ cấp/thu hồi rõ ràng. Cơ chế thực hiện và độ trễ phải được kiểm tra; không giả định mọi nền tảng hỗ trợ cùng một cách kích hoạt.

JEA hướng đến giới hạn thao tác. Trong tình huống này, thay vì cấp quyền quản trị toàn bộ cho worker thường trực, có thể cung cấp một chức năng bảo trì cụ thể với dữ liệu đầu vào được kiểm soát, danh tính riêng và log tác vụ. Việc giới hạn phải được thực thi ở cơ chế quyền hoặc giao diện tin cậy, không chỉ ở tài liệu.

Với dịch vụ cần chạy liên tục, một số quyền nghiệp vụ tối thiểu có thể phải thường trực. Mục tiêu là loại bỏ quyền quản trị không cần thiết và có căn cứ cho phần quyền phải duy trì.

## 8. Mẫu triển khai ứng dụng

Ví dụ sau là **giả mã**, không phải API của một SDK cụ thể:

~~~text
khởi_tạo_ứng_dụng:
    cấu_hình = đọc_cấu_hình_được_kiểm_soát()
    kiểm_tra_đích_nằm_trong_danh_sách_cho_phép(cấu_hình.đích)

    credential = tạo_cơ_chế_managed_identity(
        danh_tính_mong_đợi = cấu_hình.danh_tính
    )

    client = tạo_client_dịch_vụ(
        đích = cấu_hình.đích,
        credential = credential
    )

xử_lý_công_việc(công_việc):
    kiểm_tra_yêu_cầu_nghiệp_vụ(công_việc)

    thử:
        kết_quả = client.thao_tác_được_phép(công_việc.dữ_liệu)
        ghi_log(mã_công_việc, thao_tác, tài_nguyên, kết_quả_rút_gọn)
    nếu_lỗi_xác_thực:
        ghi_log_an_toàn(mã_công_việc, nhóm_lỗi, mã_tương_quan)
        thất_bại_có_kiểm_soát()
    nếu_lỗi_phân_quyền:
        ghi_log_an_toàn(mã_công_việc, thao_tác_bị_từ_chối)
        thất_bại_có_kiểm_soát()
~~~

Các quyết định cần làm rõ khi hiện thực:

- Dùng thư viện danh tính phù hợp thay vì tự viết cơ chế lưu và làm mới token nếu không cần.
- Xác định chính xác danh tính mong đợi, nhất là khi tài nguyên có nhiều danh tính.
- Phân biệt lỗi lấy token, lỗi kết nối và lỗi phân quyền.
- Có timeout và retry có giới hạn theo loại lỗi; không retry vô hạn khi thiếu quyền.
- Không ghi token, authorization header hay credential vào log.
- Không tự chuyển sang một mật khẩu quản trị dự phòng khi managed identity thất bại.

Trong Azure, việc chỉ định rõ danh tính khi có nhiều user-assigned identity giúp tránh phụ thuộc lựa chọn mặc định hoặc lỗi khi cấu hình danh tính thay đổi. [Microsoft Learn: Identity selection in token requests](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/managed-identities-faq#what-identity-will-imds-default-to-if-i-dont-specify-the-identity-in-the-request).

### Môi trường phát triển và production

Máy của lập trình viên có thể không có cùng cơ chế managed identity như môi trường chạy thật. Nếu dùng cơ chế xác thực khác trong phát triển, cần tách rõ cấu hình và danh tính.

Bài kiểm thử chỉ chạy bằng tài khoản của lập trình viên có quyền cao chưa chứng minh production hoạt động. Kiểm thử tích hợp phải chạy dưới danh tính đại diện cho workload và có quyền tương đương thiết kế.

Trong production, nếu dùng chuỗi credential có nhiều phương án, cần xác nhận phương án nào thực sự được chọn. Một secret môi trường còn sót có thể che việc managed identity chưa được sử dụng.

## 9. Kế hoạch chuyển từ credential dài hạn

### Bước 1 — Kiểm kê đường truy cập hiện tại

Ghi lại workload, người sở hữu, tài nguyên đích, thao tác, credential hiện dùng, nơi phân phối và dependency.

Không chỉ tìm chuỗi mật khẩu trong mã nguồn. Kiểm tra cả cấu hình triển khai, pipeline, tác vụ định kỳ, script vận hành và cơ chế dự phòng đã được tổ chức cho phép.

### Bước 2 — Xác nhận khả năng tương thích

Xác nhận môi trường nguồn có cơ chế danh tính phù hợp và dịch vụ đích chấp nhận cơ chế xác thực tương ứng. Nếu chưa tương thích, không thể thay mật khẩu bằng một định danh rồi kỳ vọng ứng dụng hoạt động.

Một phương án trung gian có thể là workload dùng managed identity để lấy credential còn cần thiết từ vault. Khi đó mới loại bỏ bí mật khởi tạo khỏi ứng dụng; credential của hệ thống đích vẫn cần quản lý vòng đời.

### Bước 3 — Thiết kế danh tính và quyền

Chọn ranh giới theo ứng dụng, môi trường và đặc quyền. Đặt chủ sở hữu, ghi định danh principal, tài nguyên nguồn, quyền đích và lý do.

Tách quyền triển khai hạ tầng, quyền gắn danh tính và quyền cấp quyền đích trong phạm vi tổ chức có thể thực thi.

### Bước 4 — Kiểm thử trên môi trường phù hợp

Kiểm tra:

- Luồng nghiệp vụ được phép thành công.
- Tác vụ ngoài phạm vi bị từ chối.
- Ứng dụng đang dùng đúng principal.
- Không có fallback sang credential cũ.
- Restart, thay replica hoặc thay tài nguyên có hành vi đã dự kiến.
- Log đủ đối soát và không chứa bí mật.
- Thu hồi có hiệu lực theo các điều kiện đo đã ghi nhận.

### Bước 5 — Chuyển lưu lượng có kiểm soát

Có thể chuyển một phần workload trước, đối chiếu lỗi và hành vi truy cập. Nếu có giai đoạn hai cơ chế cùng tồn tại, đặt thời hạn và người chịu trách nhiệm kết thúc.

Rollback phải là một quy trình được kiểm soát, có giới hạn và có bằng chứng. Không tạo một nhánh fallback âm thầm duy trì mật khẩu quản trị mãi mãi.

### Bước 6 — Thu hồi credential cũ

Sau khi xác nhận đường mới đáp ứng yêu cầu, thu hồi credential cũ theo kế hoạch và kiểm tra nó không còn dùng được.

Xóa secret khỏi một cấu hình không tự vô hiệu hóa bản sao đã bị lưu ở nơi khác. Trọng tâm là thu hồi hiệu lực và xử lý bản sao theo quy trình của tổ chức.

### Bước 7 — Cập nhật vận hành

Cập nhật sơ đồ dependency, runbook, cơ chế cảnh báo, kiểm kê và người sở hữu. Bàn giao cách xử lý lỗi xác thực, lỗi phân quyền và nghi ngờ workload bị kiểm soát.

## 10. Kiểm kê và quản trị vòng đời

Một managed identity ít được con người nhìn thấy vẫn có thể trở thành danh tính mồ côi hoặc có quyền không còn cần thiết. Hồ sơ nên liên kết được danh tính với chủ sở hữu và tài nguyên sử dụng.

Mẫu sau là dữ liệu kiểm kê minh họa, không phải schema của sản phẩm:

~~~yaml
identity_record:
  inventory_id: WI-INV-042
  display_name: mi-invoice-worker-prod
  identity_kind: managed-workload-identity
  assignment_model: user-assigned
  principal_reference: "<định danh principal thực tế>"
  service_owner: team-invoice
  environment: production
  purpose: process-approved-invoice-jobs
  source_resources:
    - resource_reference: "<tài nguyên chạy worker>"
      expected_workload: invoice-worker
  permissions:
    - target_reference: "<hàng đợi hóa đơn>"
      permitted_actions: receive-and-complete
      business_reason: consume-processing-jobs
    - target_reference: "<vùng lưu kết quả>"
      permitted_actions: create-processing-results
      business_reason: store-job-output
  privileged_operations: false
  approval_reference: CHANGE-EXAMPLE-042
  evidence_reference: EVID-EXAMPLE-042
  review_owner: team-identity-governance
~~~

Các giá trị như `receive-and-complete` mô tả ý định nghiệp vụ; phải ánh xạ sang quyền thật trước khi cấu hình.

### 10.1. Khi tạo hoặc gắn danh tính

Kiểm tra nguồn yêu cầu, chủ sở hữu, phạm vi, môi trường và người có quyền phê duyệt. Sau khi triển khai, đối soát trạng thái thực với hồ sơ.

Không chỉ ghi “đã có managed identity”; cần biết chính xác tài nguyên nào đang sử dụng danh tính nào.

### 10.2. Khi thay đổi workload

Một thay đổi image, lịch chạy, plugin hoặc quyền triển khai có thể làm thay đổi mức tin cậy dù role assignment chưa đổi. Rà soát danh tính trong các thay đổi có ảnh hưởng đến đường chạy mã.

Nếu chuyển một ứng dụng sang môi trường khác, không mặc định mang theo danh tính và quyền cũ. Môi trường mới có thể có dữ liệu, chủ sở hữu hoặc ranh giới tin cậy khác.

### 10.3. Khi ngừng dịch vụ

Quy trình cần xác định tài nguyên nguồn đã hết sử dụng chưa, còn workload nào dùng chung danh tính không, quyền đích nào phải bỏ và bằng chứng nào xác nhận không còn truy cập.

Trước khi xóa một danh tính dùng chung, phải đối soát toàn bộ bên sử dụng. Ngược lại, giữ danh tính lại chỉ vì “có thể còn ai đó dùng” là dấu hiệu hồ sơ chưa đầy đủ.

Khi một principal bị thay thế, không dùng tên hiển thị để kết luận quyền cũ đã chuyển sang principal mới. Cần đối chiếu định danh và quyền thực tế, đồng thời dọn các tham chiếu không còn hợp lệ theo cơ chế nền tảng.

## 11. Token, cache và thu hồi

Có ba thao tác khác nhau:

1. Ngăn workload lấy token mới dưới danh tính.
2. Thu hồi quyền của principal tại dịch vụ đích.
3. Xử lý token hoặc phiên đã tồn tại theo khả năng của dịch vụ.

Không nên coi một thao tác là bằng chứng cả ba đã hoàn tất.

Microsoft lưu ý managed identity có cơ chế cache và thay đổi membership nhóm hoặc vai trò có thể mất nhiều giờ mới phản ánh đầy đủ. Vì vậy, không dựa vào việc sửa membership như một cam kết thu hồi tức thì; phải đo và kiểm chứng trên dịch vụ liên quan. [Microsoft Learn: Managed identity authorization limitations](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/managed-identity-best-practice-recommendations#limitation-of-using-managed-identities-for-authorization).

Không áp một thời gian chờ cố định cho tất cả tình huống. Cần phân biệt token đang có, token xin mới, cache của nền tảng và cách dịch vụ đích đánh giá quyền.

### Kiểm thử thu hồi

Một bài kiểm thử có ý nghĩa nên ghi:

| Kiểm tra | Điều muốn biết |
|---|---|
| Yêu cầu nghiệp vụ mới sau thu hồi | Dịch vụ đích còn cho phép thao tác không? |
| Token đã có trước thay đổi | Đường truy cập cũ có còn tác dụng trong điều kiện thử không? |
| Yêu cầu lấy token mới | Workload còn có thể dùng quan hệ danh tính không? |
| Phiên kết nối đã mở, nếu có | Phiên còn cho phép thao tác gì? |
| Tài nguyên khác cùng dùng danh tính | Thu hồi có làm ảnh hưởng ngoài dự kiến không? |

Bằng chứng cần có thời điểm, principal, tài nguyên, thao tác và kết quả. Không lưu giá trị token trong hồ sơ chỉ để chứng minh rằng đã kiểm thử với token.

## 12. Giám sát và bằng chứng PAM

Managed identity dùng cho phần mềm không tạo ra phiên quản trị tương tác của con người trong mọi trường hợp. Vì vậy, chỉ triển khai ghi màn hình hoặc ghi phiên bastion có thể bỏ sót đường truy cập này.

Một chuỗi bằng chứng nên liên kết:

~~~text
Yêu cầu thay đổi
-> Người hoặc pipeline thực hiện triển khai
-> Phiên bản workload và tài nguyên nguồn
-> Principal được dùng
-> Thao tác tại tài nguyên đích
-> Kết quả nghiệp vụ
~~~

Không giả định một sự kiện lấy token tương ứng đúng một lần gọi dữ liệu. Ứng dụng có thể tái sử dụng token; cần đối chiếu thêm log tài nguyên đích và mã tương quan ứng dụng.

### Sự kiện nên quan tâm

Tùy khả năng nguồn log, có thể theo dõi:

- Tạo, xóa hoặc thay đổi danh tính.
- Gắn hoặc gỡ danh tính khỏi tài nguyên.
- Cấp quyền mới, đổi phạm vi hoặc thêm quan hệ phân quyền.
- Triển khai workload mới vào tài nguyên mang danh tính mạnh.
- Sử dụng danh tính trên đích hoặc thao tác không phù hợp hồ sơ.
- Tăng lỗi phân quyền bất thường.
- Danh tính không có chủ sở hữu hoặc không còn tài nguyên sử dụng rõ ràng.

Không coi bất kỳ thay đổi nào cũng là sự cố. Cảnh báo cần đối chiếu yêu cầu thay đổi, thời gian, người thực hiện và mức nhạy cảm.

Ví dụ, một danh tính của worker chỉ ghi kết quả xử lý bỗng được cấp quyền thay đổi chính sách truy cập là thay đổi đáng điều tra, ngay cả khi chưa có dấu hiệu credential bị lộ.

### Bảo vệ log

Không ghi token vào header dump, trace HTTP, log lỗi hay bản chụp cấu hình. Nếu cần ghi định danh, dùng các trường không phải bí mật và giới hạn quyền xem theo nhu cầu.

Log cũng cần được bảo vệ khỏi sửa hoặc xóa bởi chính workload trong phạm vi có thể thực hiện. Nếu ứng dụng đặc quyền có thể xóa cả bằng chứng của mình, năng lực điều tra sẽ yếu.

## 13. Ứng phó khi workload mang danh tính bị nghi xâm phạm

Mục tiêu đầu tiên là hạn chế đường sử dụng quyền trong khi duy trì khả năng phục hồi dịch vụ phù hợp.

Một runbook minh họa:

1. Xác định tài nguyên nguồn, principal, phiên bản workload và thời gian nghi bị kiểm soát.
2. Đánh giá quyền trực tiếp, quyền gián tiếp và những tài nguyên khác dùng chung danh tính.
3. Cô lập hoặc dừng nguồn bị nghi ngờ theo quyết định ứng phó.
4. Điều chỉnh quan hệ dùng danh tính và quyền đích bằng biện pháp phù hợp với nền tảng.
5. Đánh giá token, phiên và tác vụ đang chạy; kiểm chứng hiệu lực ngăn chặn.
6. Thu thập bằng chứng từ triển khai, runtime và dịch vụ đích.
7. Kiểm tra credential hoặc dữ liệu khác mà danh tính có thể đã đọc.
8. Khôi phục workload từ trạng thái tin cậy và cấp lại quyền cần thiết theo quy trình.
9. Kiểm thử nghiệp vụ, giới hạn quyền, giám sát và đóng các hành động tồn đọng.

Không tìm một mật khẩu managed identity trong mã nguồn để “đổi lại” như cách xử lý service account tự quản lý. Vấn đề có thể nằm ở quyền chạy mã, quan hệ gắn danh tính hoặc quyền đích.

Nếu danh tính đã đọc một bí mật quản trị từ vault, ngăn danh tính không tự thu hồi bản sao bí mật đã được lấy. Cần đánh giá và xử lý credential hạ nguồn theo mức ảnh hưởng.

Tương tự, nếu danh tính có quyền sửa chính sách, phải kiểm tra các quyền hoặc quan hệ tin cậy có thể đã bị tạo thêm. Khôi phục một workload chưa đủ chứng minh toàn bộ môi trường đã trở lại trạng thái tin cậy.

## 14. Những kết luận dễ sai

| Kết luận | Vì sao chưa đủ | Cách kiểm chứng phù hợp |
|---|---|---|
| Không có mật khẩu trong ứng dụng nên không cần PAM | Quyền quản trị và đường sử dụng danh tính vẫn tồn tại | Kiểm kê đặc quyền và quyền điều khiển workload |
| Token ngắn hạn nghĩa là đã có JIT | Workload có thể tiếp tục lấy token mới | Kiểm tra thời gian hiệu lực của quyền và quan hệ dùng danh tính |
| Người triển khai không xem được secret nên không có đặc quyền | Người đó có thể sửa mã chạy dưới danh tính mạnh | Phân tích khả năng thực thi mã và kiểm soát triển khai |
| Dùng chung danh tính giúp dễ kiểm toán | Có thể khó xác định workload nguồn | Đối soát principal với tài nguyên, phiên bản và mã công việc |
| Gỡ danh tính là thu hồi mọi token ngay | Token hoặc phiên cũ có thể chịu cơ chế khác | Kiểm thử nhiều đường truy cập và ghi thời điểm |
| Đọc vault là quyền ít rủi ro | Vault có thể chứa credential đặc quyền hạ nguồn | Phân tích bí mật đọc được và đường truy cập tiếp theo |
| Ứng dụng chạy trên máy lập trình viên nên production sẽ chạy | Danh tính và quyền kiểm thử có thể khác | Chạy kiểm thử dưới danh tính workload đúng thiết kế |
| Xóa tài nguyên là đã xử lý hết vòng đời quyền | Có thể còn danh tính dùng chung hoặc tham chiếu quyền | Đối soát danh tính, bên sử dụng và quyền đích sau thay đổi |

## 15. Bài thực hành thiết kế

### Bối cảnh

Một ứng dụng thử nghiệm gồm API nhận yêu cầu, worker tạo báo cáo và job bảo trì. Hiện cả ba dùng chung một credential có quyền rộng. Đội muốn chuyển sang managed identity.

Giả định môi trường chạy và các dịch vụ đích đã hỗ trợ cơ chế cần thiết. Không sử dụng tài khoản, token hoặc dữ liệu production trong bài tập.

### Nhiệm vụ

1. Lập bảng tác vụ cho từng thành phần và từng tài nguyên đích.
2. Đề xuất ranh giới danh tính, chỉ rõ trường hợp nào dùng chung và lý do.
3. Chọn mô hình vòng đời phù hợp; ghi tác động khi thay tài nguyên chạy.
4. Lập ma trận ai được tạo danh tính, gắn danh tính, triển khai mã và cấp quyền đích.
5. Viết ít nhất ba kiểm thử cho phép và ba kiểm thử từ chối.
6. Thiết kế log liên kết từ một mã công việc đến principal và thao tác tại đích.
7. Lập kế hoạch thu hồi credential cũ và kiểm chứng không có fallback.
8. Viết tình huống ứng phó khi worker bị nghi chạy mã không tin cậy.

### Kết quả mong đợi

Một phương án hợp lý tách API, worker và job bảo trì theo nhu cầu quyền. API không có quyền quản trị dữ liệu chỉ vì job bảo trì cần quyền đó. Staging không dùng danh tính production.

Kiểm thử âm tính có thể bao gồm API không đọc kho báo cáo nhạy cảm, worker không thay đổi chính sách truy cập và job bảo trì không chạy khi thiếu điều kiện phê duyệt đã thiết kế.

Báo cáo phải phân biệt điều đã kiểm thử với giả định. Nếu chưa đo độ trễ thu hồi, ghi đó là khoảng trống cần kiểm chứng thay vì tuyên bố thu hồi tức thì.

## 16. Câu hỏi tự kiểm tra

**Managed identity có thay thế mọi chức năng của PAM không?**

Không. Nó giảm phần quản lý credential nền của ứng dụng trong phạm vi được hỗ trợ. Tổ chức vẫn cần quản trị đặc quyền, quyền triển khai, phê duyệt, kiểm kê, giám sát và ứng phó.

**Một managed identity có token hợp lệ nhưng bị từ chối truy cập có mâu thuẫn không?**

Không. Xác thực danh tính và cấp quyền là hai quyết định khác nhau. Cần kiểm tra đích của token, principal thực tế, quyền hiệu lực và điều kiện truy cập.

**Khi nào dùng chung danh tính trở thành rủi ro rõ rệt?**

Khi các workload khác môi trường, khác mức tin cậy, khác nhu cầu quyền hoặc cần thu hồi độc lập nhưng lại cùng mang một danh tính mạnh.

**Vì sao quyền sửa pipeline cần được đưa vào đánh giá PAM?**

Pipeline có thể triển khai mã vào workload đặc quyền. Nếu quyền sửa pipeline dẫn đến khả năng chạy mã dưới danh tính đó, nó tạo một đường sử dụng đặc quyền.

**Nếu ứng dụng dùng managed identity để lấy mật khẩu cơ sở dữ liệu từ vault thì đã bỏ hết credential chưa?**

Chưa. Đã thay đổi cách ứng dụng khởi tạo truy cập vault, nhưng mật khẩu cơ sở dữ liệu vẫn cần phân quyền, luân chuyển, thu hồi và kiểm soát sử dụng.

**Chứng cứ nào cần có khi tuyên bố đã thu hồi quyền?**

Cần ghi biện pháp áp dụng, principal, tài nguyên, thời điểm và kết quả kiểm tra các đường liên quan như yêu cầu mới, token đang có hoặc phiên đã mở. Không suy ra toàn bộ kết quả từ một thay đổi cấu hình.

Managed identity đem lại lợi ích lớn khi được đặt trong một thiết kế quyền có chủ sở hữu và có thể kiểm chứng. Việc đánh giá phải đi từ workload đến danh tính, từ danh tính đến quyền đích, rồi quay lại những người và hệ thống có thể điều khiển workload đó.
