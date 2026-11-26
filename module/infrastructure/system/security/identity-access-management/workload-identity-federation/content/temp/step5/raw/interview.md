Workload identity federation khác gì so với việc lưu access key hoặc client secret dài hạn trong CI/CD và ứng dụng chạy trên cloud?
Trong một luồng federation điển hình, workload tạo bằng chứng danh tính, bên tin cậy xác minh bằng chứng và cấp credential ngắn hạn theo những bước nào?
Những thành phần nào cần được xác định rõ khi thiết lập trust relationship giữa một workload và cloud resource provider?
Issuer trong OIDC token đại diện cho điều gì và vì sao bên nhận phải so khớp chính xác issuer với trust configuration?
Audience claim bảo vệ workload federation khỏi loại nhầm lẫn hoặc sử dụng token sai mục đích nào?
Subject claim nên được thiết kế và kiểm tra ra sao để phân biệt repository, branch, environment, namespace hoặc service account cụ thể?
Vì sao chỉ kiểm tra chữ ký JWT hợp lệ là chưa đủ để chấp nhận một workload identity assertion?
Bạn xác minh các claim `iss`, `aud`, `sub`, `exp`, `iat` và `nbf` như thế nào trước khi đổi token lấy credential?
Bạn xử lý sai lệch đồng hồ giữa issuer, workload và security token service để tránh chấp nhận token hết hạn hoặc từ chối nhầm token hợp lệ ra sao?
Discovery document OIDC và JWKS endpoint cung cấp thông tin gì, và bên tin cậy nên bảo vệ việc truy xuất các endpoint này như thế nào?
Khi JWT chứa `kid`, verifier nên chọn khóa từ JWKS ra sao và cần xử lý thế nào nếu không tìm thấy key identifier đó?
Bạn thiết kế quy trình xoay vòng signing key của issuer để verifier chuyển từ khóa cũ sang khóa mới mà không tạo khoảng trống tin cậy như thế nào?
Những kiểm tra nào ngăn thuật toán ký yếu, `alg=none` hoặc algorithm confusion trong quá trình xác minh JWT?
Bạn xác định khi nào cần kiểm tra `nonce` hoặc `jti` để chống việc assertion bị phát lại trong một luồng federation cụ thể như thế nào?
Token có chữ ký hợp lệ nhưng được phát hành cho một audience khác thì bên nhận nên xử lý ra sao và vì sao?
Bạn ánh xạ claim từ issuer bên ngoài thành principal, role hoặc permission nội bộ theo nguyên tắc least privilege như thế nào?
Những rủi ro nào xuất hiện khi trust policy chỉ kiểm tra issuer mà không giới hạn subject và các claim ngữ cảnh khác?
Bạn thiết kế điều kiện trust cho pipeline chỉ cho phép nhánh release đã bảo vệ truy cập môi trường production như thế nào?
Làm thế nào để ngăn workflow từ pull request của fork bên ngoài nhận được cloud credential có quyền ghi vào tài nguyên nội bộ?
Bạn ràng buộc workload identity với repository, workflow file hoặc reusable workflow cụ thể ra sao để tránh một workflow khác trong cùng tổ chức dùng ké quyền?
Khi một pipeline có nhiều job với mức tin cậy khác nhau, bạn tách danh tính và quyền của từng job như thế nào?
Bạn bảo vệ trust policy trước thay đổi workflow file có thể làm pipeline hợp lệ phát hành token với subject hoặc audience ngoài dự kiến ra sao?
Protected environment, required reviewer và deployment approval nên kết hợp với workload federation như thế nào để hạn chế quyền production?
Bạn đánh giá rủi ro khi self-hosted runner được tái sử dụng giữa repository hoặc tenant có mức tin cậy khác nhau như thế nào?
Những biện pháp nào giúp bảo đảm runner CI/CD bị xâm nhập không thể giữ lại credential hoặc token của job tiếp theo?
Bạn sử dụng build provenance hoặc attestation như thế nào để bên nhận xác minh artifact đến từ pipeline và nguồn mã đã được tin cậy?
Workload identity của Kubernetes ServiceAccount được cấp và chiếu vào Pod theo cơ chế nào, và vì sao token projected có lợi hơn token dài hạn?
Bạn giới hạn một Kubernetes ServiceAccount chỉ được dùng bởi workload, namespace hoặc controller dự kiến như thế nào?
Việc bật tự động mount ServiceAccount token cho mọi Pod tạo ra rủi ro gì và bạn quyết định tắt hoặc giới hạn tính năng này ra sao?
Bạn cấu hình audience của projected ServiceAccount token để token chỉ được chấp nhận bởi đúng relying party như thế nào?
Khi Kubernetes xoay vòng projected token, ứng dụng hoặc agent cần xử lý file token thay đổi và thời hạn credential ra sao?
Những quyền Kubernetes nào có thể cho phép attacker tạo Pod, gắn ServiceAccount đặc quyền hoặc đọc token của workload khác?
Bạn ngăn một Pod ít tin cậy sử dụng node metadata service hoặc credential của node để vượt qua ranh giới workload identity như thế nào?
Trong môi trường nhiều namespace và nhiều tenant, bạn thiết kế subject mapping để hai workload trùng tên không nhận cùng một danh tính như thế nào?
Bạn phân biệt danh tính của Kubernetes node, Pod, ServiceAccount và ứng dụng bên trong Pod khi cấp quyền tới cloud resource ra sao?
Security Token Service thực hiện những bước nào khi trao đổi OIDC assertion lấy temporary cloud credential?
Bạn cấu hình trust relationship ở cloud provider để chỉ chấp nhận issuer, audience và subject thuộc workload đã được phê duyệt như thế nào?
Bạn ánh xạ federated principal sang cloud role hoặc permission set mà vẫn giới hạn tài nguyên, hành động và điều kiện truy cập ra sao?
Session policy hoặc permission boundary có thể thu hẹp quyền của credential được federation cấp như thế nào?
Bạn kiểm soát role chaining hoặc việc một credential tạm thời tiếp tục đổi lấy role khác để tránh mở rộng quyền ngoài dự kiến ra sao?
Khi một workload cần truy cập tài nguyên ở cloud account hoặc project khác, bạn thiết kế cross-account trust và xác minh principal như thế nào?
Những khác biệt nào trong mô hình trust và token exchange giữa các cloud provider cần được chuẩn hóa khi vận hành federation đa cloud?
Khi nào nên dùng OIDC federation trực tiếp và khi nào một mô hình workload identity dựa trên SPIFFE/SVID phù hợp hơn?
Bạn thiết kế thời hạn access token và temporary credential theo mức nhạy cảm của tài nguyên cùng thời gian chạy của job như thế nào?
Workload nên xử lý credential hết hạn giữa một tác vụ dài như backup hoặc deploy ra sao để không phải lưu secret dài hạn?
Bạn quản lý cache temporary credential để giảm số lần gọi STS mà không tiếp tục dùng credential sau thời điểm hết hạn như thế nào?
Vì sao workload federation không nên dựa vào refresh token có thời hạn dài và bạn xử lý việc cần credential mới như thế nào?
Bạn thiết kế cơ chế fallback khi issuer hoặc STS tạm thời không khả dụng mà không âm thầm chuyển sang static access key ra sao?
Khi workload identity token bị lộ trong log hoặc artifact, những hành động nào cần thực hiện để giới hạn khả năng sử dụng token đó?
Bạn đánh giá khả năng replay của bearer token và lựa chọn biện pháp ràng buộc token với audience, thời hạn, nonce hoặc proof-of-possession như thế nào?
Bạn thu hồi quyền của một workload đã bị compromise khi credential ngắn hạn đã được phát hành nhưng chưa hết hạn như thế nào?
Thay đổi trust policy hoặc gỡ một federated principal cần được lan truyền tới các relying party và cache quyền ra sao?
Bạn ngăn issuer domain bị chiếm quyền hoặc DNS bị điều hướng khỏi phát hành assertion được cloud provider tin cậy như thế nào?
Nếu signing key của OIDC issuer bị lộ, bạn xác định phạm vi ảnh hưởng và xử lý token đã phát hành trong khoảng thời gian compromise ra sao?
Bạn thiết kế trust policy để tránh subject collision giữa repository, namespace, tenant hoặc môi trường có tên giống nhau như thế nào?
Những claim tùy chỉnh nào có thể hữu ích để giới hạn federation theo branch, tag, workflow, environment hoặc mức độ bảo vệ nguồn mã?
Bạn kiểm soát ai được tạo, sửa hoặc xóa trust relationship và làm thế nào để ngăn quản trị viên tự mở rộng quyền của workload?
Bạn kiểm toán mối liên hệ từ workload, issuer, subject, federated principal, role được ánh xạ tới hành động trên cloud resource như thế nào?
Những trường nào cần ghi vào audit log để điều tra một lần đổi token mà không vô tình lưu JWT hoặc secret nhạy cảm?
Bạn phát hiện hành vi bất thường như một workload yêu cầu nhiều role, truy cập account lạ hoặc lấy credential ngoài lịch triển khai như thế nào?
Bạn xây dựng quy trình access review cho trust policy, claim mapping và role assignment để loại bỏ workload hoặc repository không còn hoạt động ra sao?
Bạn kiểm thử negative case cho issuer không tin cậy, audience sai, subject ngoài allowlist, token hết hạn và chữ ký không hợp lệ như thế nào?
Bạn kiểm thử việc xoay vòng JWKS khi token được ký bằng khóa cũ và khóa mới cùng tồn tại trong giai đoạn chuyển tiếp ra sao?
Bạn mô phỏng tình huống token bị đánh cắp và phát lại từ một workload khác để xác minh trust policy có giới hạn đúng ngữ cảnh không như thế nào?
Bạn kiểm chứng rằng workload không thể lấy credential production từ nhánh thử nghiệm, môi trường staging hoặc pipeline không được bảo vệ ra sao?
Bạn đo lường tỷ lệ token exchange thành công, lỗi xác minh claim, lỗi JWKS và độ trễ STS để phát hiện suy giảm federation như thế nào?
Khi issuer discovery hoặc JWKS endpoint gặp sự cố, verifier nên quyết định dùng cache khóa đã biết hay từ chối xác minh mới theo tiêu chí nào?
Bạn thiết kế fail-closed behavior cho các lỗi xác minh danh tính mà vẫn duy trì khả năng vận hành và chẩn đoán sự cố như thế nào?
Bạn giới hạn tốc độ và chống lạm dụng endpoint token exchange khi một workload hoặc runner bị lỗi vòng lặp yêu cầu credential như thế nào?
Quy trình onboarding một workload mới cần những bằng chứng, owner, scope quyền và bước phê duyệt nào trước khi thêm trust relationship?
Khi một repository, namespace, service account hoặc pipeline bị xóa, bạn bảo đảm federated trust và quyền cloud liên quan được thu hồi đầy đủ như thế nào?
Bạn xây dựng chiến lược di chuyển từ static cloud key sang workload identity federation theo từng giai đoạn mà không làm gián đoạn workload ra sao?
Bạn đánh giá một thiết kế federation end-to-end dựa trên threat model, blast radius, khả năng thu hồi và bằng chứng audit như thế nào?
