# Mở tính năng theo nhóm người dùng hoặc từng giai đoạn

Một bản build mới không nhất thiết phải làm mọi người dùng nhìn thấy tính năng mới ngay lập tức. Nhóm có thể triển khai mã lên production nhưng giữ tính năng ở trạng thái tắt, sau đó mở cho nhân viên nội bộ, một nhóm khách hàng thử nghiệm hoặc một tỷ lệ người dùng nhỏ. Khi dữ liệu vận hành cho thấy tính năng ổn định và mang lại kết quả mong đợi, nhóm mới mở rộng dần đến các nhóm tiếp theo.

Cách phát hành này thường dùng **feature flag (cờ tính năng)** kết hợp với **staged rollout hoặc progressive rollout (mở tính năng theo giai đoạn)**. Nó tách thời điểm triển khai mã khỏi thời điểm người dùng được tiếp cận hành vi mới, giúp giới hạn phạm vi ảnh hưởng và tạo cơ hội dừng hoặc thu hẹp rollout khi có vấn đề.

Đây là một phần của năng lực **DEVOPS_CI_CD_FUNDAMENTALS**: xây dựng tư duy CI/CD từ sự kiện Git, pipeline dưới dạng mã, build và kiểm thử tự động đến quản lý artifact, môi trường, cổng chất lượng, phát hành có truy vết, bảo vệ bí mật, xác minh sau triển khai và khả năng quay lui.

## 1. Phân biệt deploy, release và exposure

Ba thời điểm này thường bị gọi chung là “phát hành”, nhưng chúng biểu thị những việc khác nhau:

- **Deploy:** đưa artifact hoặc phiên bản ứng dụng lên một môi trường.
- **Release:** cho phép một khả năng hoặc thay đổi sản phẩm được sử dụng.
- **Exposure:** người dùng hoặc nhóm người dùng thực sự nhìn thấy hay sử dụng tính năng.

Ví dụ, nhóm triển khai phiên bản 2.4.0 lên production vào thứ Hai nhưng giữ tính năng thanh toán bằng ví điện tử ở trạng thái tắt. Ngày thứ Ba, nhóm mở cho nhân viên nội bộ. Ngày thứ Tư, mở cho 5% tài khoản đủ điều kiện. Nếu số liệu ổn định, nhóm tiếp tục tăng tỷ lệ trong các ngày sau.

Trong ví dụ này, artifact đã được deploy trước khi tính năng được release rộng rãi. Nhóm có thể sửa lỗi, xác minh cấu hình và chuẩn bị vận hành trước khi bật tính năng cho nhiều người dùng.

Tách các khái niệm giúp pipeline có hai loại quyết định:

1. Quality gate xác định artifact có đủ điều kiện triển khai hay không.
2. Rollout gate xác định tính năng có đủ điều kiện mở rộng đến nhóm người dùng tiếp theo hay không.

Feature flag không thay thế kiểm thử, quality gate hoặc quy trình rollback. Nó là một cơ chế điều khiển exposure trong khi mã đã tồn tại trong ứng dụng.

## 2. Feature flag là gì?

Feature flag là một điều kiện cấu hình cho phép ứng dụng chọn hành vi tại runtime. Thay vì phải tạo một bản build mới để bật hoặc tắt một tính năng, ứng dụng đọc trạng thái flag và quyết định nhánh xử lý.

Ví dụ đơn giản:

~~~java
if (featureFlags.isEnabled("new-checkout", userContext)) {
    return newCheckoutService.checkout(request);
}

return legacyCheckoutService.checkout(request);
~~~

Flag có thể được lưu trong cấu hình ứng dụng, database, dịch vụ quản lý feature flag hoặc nền tảng progressive delivery. Điều quan trọng là ứng dụng có thể đánh giá flag theo một ngữ cảnh xác định và nhóm có thể thay đổi phạm vi exposure theo quy trình được kiểm soát.

### 2.1. Những loại flag thường gặp

| Loại flag | Mục đích | Vòng đời thường thấy |
| --- | --- | --- |
| Release toggle | Ẩn tính năng mới cho đến khi sẵn sàng phát hành | Tạm thời; nên xóa sau khi rollout hoàn tất |
| Experiment toggle | Chia người dùng vào các biến thể để đo tác động | Có thời hạn theo kế hoạch thử nghiệm |
| Operational kill switch | Tắt nhanh hành vi có nguy cơ gây sự cố | Có thể tồn tại lâu hơn nhưng phải được kiểm tra và quản trị |
| Permission/entitlement toggle | Kiểm soát quyền sử dụng theo gói dịch vụ hoặc entitlement | Thường gắn với mô hình quyền nghiệp vụ |

Không nên dùng một flag cho nhiều mục tiêu không liên quan. Ví dụ, flag dùng để bật một tính năng trong quá trình release không nên đồng thời trở thành cơ chế cấp quyền truy cập dữ liệu nhạy cảm. Quyền nghiệp vụ cần được kiểm tra bằng authorization policy độc lập.

## 3. Mở theo nhóm người dùng và theo tỷ lệ

Có hai cách phổ biến để giới hạn exposure:

**Targeting theo nhóm (cohort targeting):** chỉ bật cho những người dùng đáp ứng điều kiện, chẳng hạn nhân viên nội bộ, tài khoản thử nghiệm, một nhóm khách hàng đã đăng ký hoặc tenant được chọn.

**Percentage rollout:** bật cho một tỷ lệ xác định của nhóm đủ điều kiện, chẳng hạn 1%, 5%, 10%, 25%, 50% rồi 100%.

Có thể kết hợp cả hai. Ví dụ, trước tiên chỉ nhân viên nội bộ được sử dụng; sau đó mở 5% khách hàng ở một khu vực; tiếp theo mở 20% tài khoản trả phí; cuối cùng mở cho toàn bộ người dùng đủ điều kiện.

Các nhóm thường được lựa chọn:

- Nhân viên hoặc tài khoản nội bộ (dogfooding).
- Nhóm khách hàng tham gia chương trình beta.
- Tenant hoặc tổ chức đối tác đã đồng ý thử nghiệm.
- Người dùng thuộc một khu vực hoặc nền tảng cụ thể.
- Một tỷ lệ người dùng được chọn ngẫu nhiên có kiểm soát.
- Người dùng đang dùng phiên bản ứng dụng đáp ứng điều kiện tương thích.

Nhóm cần định nghĩa điều kiện rõ ràng, có thể kiểm tra và có owner. Tránh các điều kiện mơ hồ như “một số khách hàng quan trọng” nếu không có danh sách hoặc quy tắc xác định.

## 4. Quy trình staged rollout

Một rollout theo giai đoạn thường đi qua các bước:

1. **Dark launch:** deploy mã lên production nhưng flag tắt, xác minh ứng dụng khởi động và nhánh cũ vẫn hoạt động.
2. **Internal rollout:** mở cho nhân viên hoặc tài khoản kiểm thử.
3. **Limited cohort:** mở cho một nhóm nhỏ đã được chọn.
4. **Small percentage:** mở cho tỷ lệ nhỏ trong tập người dùng đủ điều kiện.
5. **Progressive expansion:** tăng tỷ lệ theo các mốc đã định.
6. **General availability:** mở cho toàn bộ nhóm đủ điều kiện.
7. **Cleanup:** loại bỏ nhánh mã cũ và release flag khi không còn cần.

Sơ đồ:

~~~mermaid
flowchart TD
    A["Deploy artifact với flag OFF"] --> B["Smoke test và kiểm tra nhánh cũ"]
    B --> C["Mở cho nhân viên nội bộ"]
    C --> D["Đánh giá metrics và feedback"]
    D --> E{"Đạt guardrails?"}
    E -- "Không" --> X["Dừng rollout / tắt flag"]
    E -- "Có" --> F["Mở cohort nhỏ"]
    F --> G["Đánh giá theo cửa sổ quan sát"]
    G --> H{"Đạt guardrails?"}
    H -- "Không" --> X
    H -- "Có" --> I["Tăng tỷ lệ từng bước"]
    I --> J{"Đã đủ điều kiện GA?"}
    J -- "Chưa" --> G
    J -- "Rồi" --> K["Mở cho toàn bộ nhóm đủ điều kiện"]
    K --> L["Theo dõi và dọn release flag"]
~~~

Không có một lịch rollout cố định phù hợp với mọi sản phẩm. Một dịch vụ có hàng triệu request mỗi giờ có thể thu thập đủ dữ liệu nhanh; một sản phẩm B2B có vài chục giao dịch mỗi ngày cần thời gian quan sát dài hơn. Mỗi giai đoạn phải có điều kiện tiếp tục, dừng hoặc quay lại rõ ràng.

## 5. Xác định cohort ổn định và nhất quán

Khi chọn người dùng theo tỷ lệ, cùng một người nên nhận cùng một quyết định trong suốt rollout, trừ khi chính sách chủ động thay đổi assignment.

Nếu mỗi request chọn ngẫu nhiên độc lập, người dùng có thể thấy giao diện mới ở request này và giao diện cũ ở request tiếp theo. Điều đó gây khó hiểu, làm hỏng session hoặc khiến số liệu phân tích không nhất quán.

### 5.1. Deterministic bucketing

Một cách phổ biến là tính bucket từ flag key và một định danh ổn định của người dùng hoặc tenant:

~~~text
input = flag_key + ":" + stable_subject_id + ":" + rollout_salt
hash_value = SHA256(input)
bucket = unsigned_first_64_bits(hash_value) mod 10000
enabled = bucket < rollout_percentage * 100
~~~

Với 10.000 bucket, mỗi bucket tương ứng 0,01%. Nếu tỷ lệ rollout là 5%, hệ thống bật flag cho bucket từ 0 đến 499. Cùng một subject ID, flag key và salt sẽ cho cùng bucket.

Định danh subject có thể là user ID nội bộ hoặc tenant ID tùy phạm vi rollout. Không nên đưa email, số điện thoại hoặc thông tin nhận dạng trực tiếp vào key gửi tới dịch vụ bên ngoài. Hash một email không tự động biến dữ liệu đó thành dữ liệu vô danh; cần dùng định danh giả danh phù hợp và kiểm soát quyền truy cập.

### 5.2. Giữ assignment khi tăng tỷ lệ

Nếu dùng cùng thuật toán, key và salt, việc tăng tỷ lệ từ 5% lên 10% sẽ giữ nhóm 5% ban đầu và thêm những subject thuộc bucket tiếp theo. Đây là đặc tính hữu ích của deterministic bucketing.

Không thay salt hoặc cách tính bucket giữa các giai đoạn nếu muốn cohort cũ được giữ nguyên. Nếu cần thay đổi cohort có chủ đích, hãy tạo một rollout hoặc experiment mới và ghi lại thời điểm thay đổi.

### 5.3. Chọn đơn vị phân nhóm phù hợp

Với sản phẩm cá nhân, có thể phân nhóm theo user ID. Với sản phẩm B2B, nên cân nhắc tenant/account ID để mọi người trong cùng tổ chức có trải nghiệm nhất quán. Với hệ thống nhiều thiết bị, có thể cần assignment gắn với account thay vì thiết bị.

Nếu một tenant có nhiều người dùng và chỉ một số người thấy tính năng mới, họ có thể không chia sẻ được dữ liệu hoặc quy trình với đồng nghiệp. Đơn vị phân nhóm cần phù hợp với ranh giới nghiệp vụ.

## 6. Thiết kế targeting rules

Targeting rule quyết định ai đủ điều kiện trước khi áp dụng percentage rollout. Ví dụ:

~~~yaml
feature:
  key: new-checkout
  enabled: true
  targeting:
    allowlist:
      - user-test-001
      - tenant-beta-042
    rules:
      - attribute: region
        operator: in
        values: [vn, sg]
      - attribute: app_version
        operator: greater_than_or_equal
        value: 2.4.0
    rollout:
      percentage: 5
      subject: tenant_id
      salt: checkout-rollout-2026-01
~~~

Đây là cấu hình minh họa; thứ tự kết hợp allowlist, rules và percentage phải được định nghĩa rõ trong hệ thống flag. Không mặc định rằng mọi rule trong danh sách đều là OR hay AND nếu công cụ chưa quy định.

Các câu hỏi cần trả lời:

- Allowlist có ưu tiên hơn rule chung không?
- Người dùng không có attribute cần thiết sẽ được xử lý thế nào?
- Nhiều rule được kết hợp theo AND hay OR?
- Tenant bị loại khỏi rollout có thể vào qua allowlist không?
- Khi cập nhật targeting, assignment cũ có thay đổi không?
- Có thể truy vết phiên bản cấu hình nào đã quyết định exposure không?

Targeting nên được kiểm tra tự động bằng test case cho cả trường hợp được bật, bị tắt, thiếu attribute, sai định dạng và xung đột rule. Không để lỗi parsing cấu hình làm tính năng vô tình mở rộng cho toàn bộ người dùng.

## 7. Quyết định mở rộng dựa trên guardrails

Mỗi giai đoạn cần có tiêu chí đánh giá được thống nhất trước khi mở rộng. Không nên tăng tỷ lệ chỉ vì “chưa thấy ai phàn nàn”.

### 7.1. Guardrails kỹ thuật

- Error rate và tỷ lệ request thất bại.
- Latency p50, p95 và p99.
- Timeout, retry và connection error.
- CPU, memory, thread pool và connection pool.
- Database load, lock, query latency.
- Queue lag và số message lỗi.
- Crash rate trên mobile hoặc desktop client.

### 7.2. Guardrails nghiệp vụ

- Tỷ lệ hoàn tất quy trình chính.
- Tỷ lệ thanh toán hoặc giao dịch thành công.
- Tỷ lệ hủy, hoàn tiền hoặc thao tác bị bỏ dở.
- Số lượng ticket hỗ trợ và phản hồi tiêu cực.
- Tỷ lệ người dùng quay lại hoặc hoàn tất hành động mong muốn.

Chỉ số thành công của tính năng cần được phân biệt với guardrail. Ví dụ, mục tiêu là tăng tỷ lệ hoàn tất checkout, nhưng guardrail là không làm tăng lỗi thanh toán, thời gian phản hồi hoặc tỷ lệ hoàn tiền.

### 7.3. Đặt ngưỡng và cửa sổ quan sát

Ngưỡng cần dựa trên baseline, SLO và mức độ quan trọng của luồng nghiệp vụ. Ví dụ minh họa:

| Tín hiệu | Điều kiện tiếp tục | Điều kiện dừng/đánh giá lại |
| --- | --- | --- |
| HTTP 5xx | Không vượt baseline cộng biên cho phép | Tăng vượt ngưỡng đã định trong cửa sổ quan sát |
| p95 latency | Nằm trong SLO | Vượt SLO liên tục hoặc tăng mạnh so với baseline |
| Payment success | Không suy giảm đáng kể | Giảm vượt ngưỡng hoặc có giao dịch sai |
| Crash-free sessions | Trong mục tiêu chất lượng | Crash tăng theo phiên bản hoặc cohort |
| Queue lag | Ổn định trong giới hạn | Tăng kéo dài, gây trễ nghiệp vụ |

Các con số cụ thể phải do owner của dịch vụ đặt dựa trên dữ liệu thực tế. Với traffic thấp, cần thời gian quan sát dài hơn để tránh kết luận từ vài request. Với sự cố nghiêm trọng như sai lệch dữ liệu hoặc thanh toán trùng, không cần chờ hết cửa sổ thống kê mới dừng rollout.

## 8. Quan sát exposure và hành vi của từng cohort

Để hiểu tính năng có hoạt động tốt hay không, cần biết người dùng nào được đánh giá flag, ai thực sự được exposure và họ gặp kết quả gì.

Nên ghi nhận các sự kiện:

- Flag evaluation: hệ thống đã đánh giá flag với kết quả nào.
- Assignment: subject được xếp vào cohort hoặc biến thể nào.
- Exposure: tính năng thực sự được hiển thị hoặc sử dụng.
- Outcome: hành động nghiệp vụ sau exposure.

Không phải mọi lần đánh giá flag đều là exposure. Một request backend có thể kiểm tra flag nhưng người dùng chưa nhìn thấy giao diện hoặc chưa thực hiện hành động. Nếu dùng evaluation event làm mẫu số cho conversion, kết quả có thể sai.

Metrics và log nên gắn với:

- Flag key và phiên bản cấu hình.
- Cohort/variant hoặc rollout stage.
- Application version và artifact digest khi cần.
- Region, platform hoặc tenant segment theo chính sách.
- Request/correlation ID để điều tra.

Tránh ghi định danh cá nhân trực tiếp vào metrics label vì có thể làm tăng cardinality và lộ dữ liệu. Dùng ID giả danh hoặc aggregate phù hợp; giới hạn thời gian lưu và quyền truy cập.

## 9. Feature rollout khác gì A/B testing?

Staged rollout và A/B testing có thể cùng sử dụng feature flag nhưng trả lời câu hỏi khác nhau:

| Nội dung | Staged rollout | A/B testing |
| --- | --- | --- |
| Mục tiêu | Giảm rủi ro khi phát hành và xác minh độ ổn định | Đo tác động nhân quả tương đối giữa các biến thể |
| Nhóm người dùng | Tăng dần theo allowlist hoặc tỷ lệ | Phân nhóm theo thiết kế thử nghiệm |
| Tiêu chí mở rộng | Guardrails kỹ thuật/nghiệp vụ đạt | Đủ mẫu và phân tích thống kê theo kế hoạch |
| Thời gian | Theo rủi ro và mức độ ổn định | Theo thời lượng cần để thu thập mẫu |
| Kết quả | Quyết định tiếp tục, dừng hoặc mở rộng release | Chọn biến thể hoặc kết luận không có khác biệt đáng tin |

Không nên tuyên bố một tính năng tốt hơn chỉ vì cohort được mở 10% có conversion cao hơn nhóm còn lại. Cohort có thể khác nhau về khu vực, thời điểm, loại tài khoản hoặc hành vi trước đó. A/B testing cần phân nhóm ngẫu nhiên theo thiết kế, xác định metric chính, cỡ mẫu, thời lượng và cách xử lý nhiều phép so sánh.

Trong staged rollout, nhóm có thể dùng dữ liệu cohort để phát hiện lỗi, nhưng mục tiêu chính là an toàn phát hành. Nếu muốn đo tác động sản phẩm, hãy thiết kế experiment riêng hoặc bổ sung phương pháp phân tích phù hợp.

## 10. Kill switch và cách dừng rollout

Kill switch là cơ chế tắt nhanh một hành vi khi có sự cố. Nó hữu ích khi rollout phát hiện lỗi nghiêm trọng, nhưng cần được thiết kế và kiểm tra trước.

Một kill switch tốt:

- Có thể được kích hoạt bởi người có quyền phù hợp hoặc automation theo policy.
- Có thời gian lan truyền cấu hình được biết và đo được.
- Có default behavior an toàn khi dịch vụ flag không truy cập được.
- Có log/audit cho người thay đổi, thời điểm và lý do.
- Không phụ thuộc chính tính năng đang gặp lỗi để tự tắt.
- Được diễn tập trong staging hoặc môi trường thử nghiệm.

Default khi không đọc được flag phải được chọn theo rủi ro. Với một tính năng mới chưa được chứng minh, default OFF thường an toàn hơn. Với một chức năng vận hành thiết yếu đã ổn định, tắt mặc định có thể làm hệ thống ngừng hoạt động. Hãy định nghĩa fallback theo từng flag, không áp dụng một quy tắc máy móc.

Tắt flag cũng không luôn đảo ngược side effect đã xảy ra. Nếu tính năng đã ghi dữ liệu theo schema mới, gửi message, tạo giao dịch hoặc gửi email, kill switch chỉ ngăn hành vi tiếp theo. Cần quy trình xử lý dữ liệu và giao dịch đã phát sinh.

## 11. Tính nhất quán khi flag được đánh giá ở nhiều nơi

Một ứng dụng phân tán có thể đánh giá cùng flag tại frontend, backend, worker và nhiều service. Nếu mỗi nơi nhận một phiên bản cấu hình khác nhau, người dùng có thể gặp hành vi không nhất quán.

Hãy quyết định:

- Flag được đánh giá ở client hay server?
- Server có là nguồn quyết định cuối cùng cho hành động nhạy cảm không?
- Cấu hình được cache bao lâu?
- Khi flag service mất kết nối, dùng giá trị cuối cùng hay fallback?
- Làm sao đảm bảo frontend và backend hiểu cùng cohort?
- Có cần truyền assignment trong request context hoặc token nội bộ không?

Với quyền truy cập dữ liệu, thanh toán hoặc hành động bảo mật, backend phải kiểm tra authorization độc lập. Không tin quyết định flag từ client vì người dùng có thể sửa request hoặc chạy phiên bản client cũ.

Với mobile app, client có thể không cập nhật trong nhiều tuần hoặc nhiều tháng. Backend cần tương thích với phiên bản cũ; không thể giả định mọi thiết bị nhận cấu hình và code mới cùng lúc.

## 12. Tương thích dữ liệu và side effects trong rollout

Mở tính năng theo nhóm có nghĩa là nhiều phiên bản hành vi cùng tồn tại. Một phần người dùng có thể ghi dữ liệu theo format mới trong khi nhóm khác vẫn dùng format cũ.

Áp dụng các nguyên tắc:

- Mở rộng schema trước, loại bỏ schema cũ sau khi không còn client cần dùng.
- Giữ API tương thích ngược trong thời gian rollout.
- Dùng idempotency key cho thao tác có side effect.
- Đảm bảo event schema có version và consumer xử lý được cả phiên bản liên quan.
- Tránh để cùng một tenant bị chia vào hai luồng dữ liệu không tương thích.
- Có kế hoạch backfill và xử lý dữ liệu nếu phải tắt tính năng.

Ví dụ, tính năng checkout mới thêm trường payment_method_v2. Trước khi bật cho khách hàng, database có thể thêm trường mới theo cách nullable; backend vẫn đọc được dữ liệu cũ. Sau khi rollout hoàn tất và mọi luồng đã chuyển, nhóm mới lên kế hoạch loại bỏ trường cũ trong một thay đổi riêng.

Nếu tính năng chỉ hiển thị giao diện mới nhưng gọi cùng API ổn định, rủi ro dữ liệu có thể thấp hơn. Nếu tính năng thay đổi logic ghi tiền, tồn kho hoặc quyền truy cập, cần đánh giá kỹ hơn và có guardrail nghiệp vụ chặt hơn.

## 13. Bảo mật và quyền riêng tư trong targeting

Targeting có thể sử dụng region, tenant, plan, app version hoặc thuộc tính tài khoản. Đây là dữ liệu có thể ảnh hưởng đến quyền lợi người dùng và đôi khi chứa thông tin nhạy cảm.

Thực hành nên áp dụng:

- Chỉ dùng thuộc tính cần thiết cho mục tiêu rollout.
- Không dùng thuộc tính nhạy cảm hoặc dữ liệu cá nhân nếu không có căn cứ và phê duyệt phù hợp.
- Không để client tự khai báo thuộc tính có thể mở khóa quyền lợi.
- Xác thực tenant/user context từ nguồn tin cậy ở server.
- Giới hạn ai được thay đổi targeting rule và percentage.
- Audit mọi thay đổi flag, đặc biệt flag ảnh hưởng payment, access hoặc dữ liệu.
- Không ghi PII vào log hoặc metric label.

Feature flag không phải authorization. Nếu flag mở cho một cohort, backend vẫn phải kiểm tra user có quyền truy cập tài nguyên hay không. Người dùng ngoài cohort không được phép gọi trực tiếp API để vượt qua giao diện đã ẩn.

## 14. Tích hợp staged rollout vào CI/CD

Pipeline có thể chia thành hai luồng liên quan:

**Luồng build và deploy**

1. Checkout commit đã review.
2. Build artifact và chạy test.
3. Chạy quality gate, scan và tạo provenance/SBOM nếu policy yêu cầu.
4. Deploy artifact lên production với release flag ở trạng thái OFF.
5. Chạy smoke test cho nhánh cũ và kiểm tra khả năng đánh giá flag.

**Luồng mở rộng feature**

1. Kiểm tra owner, mục tiêu, cohort và guardrails.
2. Phê duyệt thay đổi targeting hoặc rollout percentage.
3. Cập nhật flag config theo phiên bản có audit.
4. Quan sát metrics theo cohort và application version.
5. Tự động hoặc thủ công đánh giá điều kiện mở rộng.
6. Tăng tỷ lệ, giữ nguyên, dừng hoặc tắt flag.
7. Khi đạt GA, lên lịch xóa flag và mã cũ.

Không nhất thiết mọi thay đổi percentage đều cần build lại artifact. Cấu hình flag có thể được quản lý riêng, nhưng cần kiểm soát truy cập, review, audit và khả năng rollback cấu hình.

### 14.1. Ví dụ rollout configuration

~~~yaml
release:
  feature: new-checkout
  owner: team-commerce
  artifact:
    version: 2.4.0
    digest: sha256:example-digest
  stages:
    - name: internal
      target: allowlist
      approval: product-and-engineering
    - name: beta
      target:
        tenants: [tenant-beta-01, tenant-beta-02]
      observation_window: 24h
    - name: percentage-5
      percentage: 5
      observation_window: 2h
    - name: percentage-25
      percentage: 25
      observation_window: 4h
    - name: general-availability
      percentage: 100
      approval: release-owner
  guardrails:
    max_error_rate: defined-by-service-slo
    latency_slo: defined-by-service-slo
    business_metric: checkout_success_rate
  rollback:
    action: disable-feature-flag
    owner: on-call-commerce
~~~

Đây là cấu hình minh họa, không phải schema của một CI platform. Giá trị ngưỡng cần được thay bằng SLO thực tế. Trong hệ thống thật, phải định nghĩa thứ tự stage, điều kiện chuyển tiếp, cách tính percentage, cách xử lý flag service unavailable và ai được phê duyệt.

### 14.2. Tự động hóa điều kiện mở rộng

Một policy có thể mô tả logic:

~~~text
if all_required_metrics_are_available
   and error_rate <= approved_error_threshold
   and latency_p95 <= approved_latency_threshold
   and business_guardrails_pass
   and observation_window_completed:
       allow_next_stage
else:
       hold_rollout

if critical_incident_detected:
       disable_feature_flag
       notify_on_call
       create_incident_record
~~~

Đây là pseudo-policy. Trong triển khai thật, cần xử lý dữ liệu metrics thiếu, độ trễ telemetry, traffic thấp, alert nhiễu và quyền thực hiện hành động tự động. Không nên tự động mở rộng nếu hệ thống giám sát không cung cấp đủ dữ liệu để đánh giá.

## 15. Quản lý vòng đời và dọn dẹp feature flag

Flag giúp rollout linh hoạt nhưng mỗi flag cũng tạo thêm nhánh logic cần kiểm thử. Nếu không dọn, codebase sẽ tích lũy nhiều trạng thái khó hiểu.

Mỗi flag nên có metadata:

- Key duy nhất và mô tả hành vi.
- Loại flag và lý do tồn tại.
- Owner kỹ thuật/sản phẩm.
- Ngày tạo và ngày dự kiến review hoặc hết hạn.
- Giá trị mặc định an toàn.
- Các cohort và điều kiện targeting.
- Artifact/version có sử dụng flag.
- Trạng thái rollout và kế hoạch cleanup.

Sau khi rollout hoàn tất:

1. Xác nhận tính năng đã đạt general availability hoặc quyết định dừng.
2. Ghi nhận trạng thái cuối và cấu hình mặc định.
3. Xóa nhánh code cũ hoặc nhánh thử nghiệm không còn dùng.
4. Xóa flag khỏi dịch vụ cấu hình và test không còn cần thiết.
5. Giữ audit record và dữ liệu phân tích theo chính sách lưu trữ.

Operational kill switch hoặc permission flag có thể cần tồn tại lâu dài. Những flag này vẫn cần owner, tài liệu, test và kiểm tra định kỳ. Không xóa kill switch chỉ vì release flag đã được dọn.

## 16. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Mở 100% ngay sau deploy | Lỗi mới ảnh hưởng toàn bộ người dùng | Bắt đầu bằng cohort nhỏ và guardrails |
| Random lại mỗi request | Người dùng thấy hành vi không nhất quán | Deterministic bucketing theo subject ổn định |
| Thay salt giữa rollout | Cohort bị xáo trộn | Giữ key/salt ổn định hoặc tạo rollout mới có chủ đích |
| Dùng flag như cơ chế phân quyền | Người dùng có thể gọi API trực tiếp | Authorization độc lập ở backend |
| Chỉ theo dõi metrics tổng | Lỗi trong cohort mới bị che khuất | Tách metrics theo flag, stage và version |
| Coi evaluation là exposure | Mẫu số phân tích bị sai | Ghi exposure khi người dùng thực sự tiếp cận |
| Không có kill switch | Khó dừng nhanh khi có sự cố | Thiết kế, phân quyền và diễn tập tắt flag |
| Flag service lỗi làm bật tính năng mới | Hành vi ngoài dự kiến khi dependency mất kết nối | Định nghĩa fallback an toàn cho từng flag |
| Hai phiên bản ghi dữ liệu không tương thích | Rollback gây lỗi hoặc mất dữ liệu | Expand-contract và kiểm tra tương thích |
| Không dọn release flag | Code và test tích lũy nhánh cũ | Gán owner, expiry và cleanup task |
| Dùng rollout để kết luận A/B test | Kết luận sản phẩm sai lệch | Thiết kế experiment và phân tích thống kê riêng |

## 17. Checklist trước khi mở rộng tính năng

**Thiết kế flag và cohort**

- [ ] Flag có key, loại, mô tả và owner.
- [ ] Đã xác định nhóm người dùng hoặc đơn vị tenant phù hợp.
- [ ] Percentage rollout dùng assignment ổn định.
- [ ] Targeting rules có thứ tự và logic kết hợp rõ ràng.
- [ ] Fallback khi flag service lỗi đã được xác định.
- [ ] Flag không thay thế authorization.

**An toàn và khả năng quan sát**

- [ ] Artifact đã qua quality gate và được truy vết bằng digest.
- [ ] Có smoke test cho nhánh cũ và mới.
- [ ] Metrics kỹ thuật và nghiệp vụ được tách theo cohort/version.
- [ ] Có ngưỡng dừng và cửa sổ quan sát.
- [ ] Có kill switch và người có quyền kích hoạt.
- [ ] Không ghi PII hoặc secret vào log/metrics.

**Dữ liệu và vận hành**

- [ ] API, database schema và event tương thích trong thời gian rollout.
- [ ] Side effects có idempotency hoặc cơ chế giới hạn.
- [ ] Mobile/client cũ được xem xét.
- [ ] Có owner và quy trình phê duyệt từng giai đoạn.
- [ ] Có kế hoạch rollback flag và xử lý dữ liệu đã phát sinh.
- [ ] Có ngày review/cleanup cho release flag.

## Kết luận

Mở tính năng theo nhóm hoặc từng giai đoạn giúp tách việc deploy artifact khỏi việc đưa hành vi mới đến người dùng. Feature flag, cohort targeting và deterministic bucketing cho phép kiểm soát ai được sử dụng tính năng; staged rollout giúp tăng exposure theo từng bước dựa trên guardrails và dữ liệu vận hành.

Một rollout đáng tin cậy cần có tiêu chí tiếp tục/dừng, metrics theo cohort, kill switch, kiểm soát dữ liệu và side effects, quyền targeting phù hợp và kế hoạch dọn flag. Khi các điều kiện này được đưa vào quy trình CI/CD có audit và truy vết, nhóm có thể phát hành thường xuyên hơn mà vẫn giới hạn phạm vi ảnh hưởng và phục hồi nhanh khi phát hiện vấn đề.
