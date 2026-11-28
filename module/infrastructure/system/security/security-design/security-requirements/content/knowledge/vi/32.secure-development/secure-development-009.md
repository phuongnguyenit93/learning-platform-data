# Fuzz testing

## 1. Fuzz testing cần tìm và chứng minh điều gì?

**Fuzz testing**, thường gọi là fuzzing, là cách thực thi một mục tiêu kiểm thử nhiều lần với các đầu vào hoặc chuỗi thao tác được tạo, biến đổi và lựa chọn có hệ thống, đồng thời quan sát dấu hiệu vi phạm một oracle. Đầu vào có thể là bytes, tài liệu có cấu trúc, request hoặc một chuỗi hành động có trạng thái.

**Oracle** là quy tắc xác định kết quả nào được phép và kết quả nào là lỗi. Crash, timeout hoặc lỗi kiểm tra bộ nhớ là những oracle phổ biến, nhưng bảo mật còn cần oracle về quyền truy cập, dữ liệu, tác động phụ và giới hạn tài nguyên. Một API trả HTTP 200 cho dữ liệu của tenant khác có thể vi phạm nghiêm trọng dù tiến trình không crash.

Trong chương **Secure development** của module yêu cầu bảo mật, fuzzing cần liên kết với rủi ro và bất biến cụ thể. “Chạy fuzzer một đêm” chưa xác định mục tiêu, điều kiện lỗi, phạm vi, môi trường, khả năng tái hiện và tiêu chí chấp nhận thay đổi.

Ví dụ: bộ nhập báo cáo phải từ chối dữ liệu sai định dạng, giới hạn độ sâu và không cấp quyền cho report ngoài tenant. Một chiến dịch chỉ gọi parser với bytes ngẫu nhiên có thể tìm lỗi parser nhưng chưa kiểm tra được hành vi phân quyền của service dùng parser đó.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Chọn target theo entry point, ranh giới tin cậy và mức tác động.
2. Chuyển yêu cầu bảo mật thành oracle có thể quan sát.
3. Thiết kế harness, corpus và chiến lược sinh dữ liệu phù hợp.
4. Quản lý giới hạn, tính lặp lại, giảm mẫu lỗi và quy trình xử lý finding.
5. Đặc tả gate CI và acceptance criteria mà không suy kết quả sạch thành bằng chứng không còn lỗ hổng.

## 2. Fuzzing khác gì kiểm thử bằng một bộ ví dụ cố định?

### 2.1. Các cách tạo và dẫn hướng đầu vào

| Cách tiếp cận | Cơ chế chính | Điều cần lưu ý |
|---|---|---|
| Mutation-based | Biến đổi seed/corpus bằng thay bytes, xóa, lặp, ghép hoặc đổi trường | Seed tốt giúp đi qua lớp kiểm tra định dạng ban đầu |
| Generation/grammar-based | Sinh dữ liệu theo cấu trúc/ngữ pháp đã mô tả | Cần chủ động thử cả cấu trúc hợp lệ và vi phạm ràng buộc |
| Coverage-guided | Dùng tín hiệu thực thi để ưu tiên đầu vào mở đường code mới | Chỉ có ý nghĩa khi instrumentation và tín hiệu hoạt động đúng |
| Black-box | Quan sát đầu ra/hành vi mà không cần coverage nội bộ | Khó biết phần code nào chưa được chạm tới |
| Stateful/model-based | Sinh chuỗi hành động và đối chiếu trạng thái với mô hình | Cần reset, mô hình quyền và quy tắc chuyển trạng thái đúng |

Các cách trên có thể kết hợp. Mutation không bắt buộc chỉ tạo dữ liệu vô nghĩa; một mutator có cấu trúc có thể giữ phần lớn tài liệu hợp lệ rồi phá một ràng buộc. Ngược lại, dữ liệu đúng grammar vẫn có thể sai ngữ nghĩa nghiệp vụ hoặc gây cạn tài nguyên.

Fuzzing và property-based testing có phần giao nhau ở việc sinh nhiều đầu vào và kiểm tra thuộc tính. Một chiến dịch bảo mật cần mô tả cách sinh, dẫn hướng, oracle và bằng chứng thực tế; tên công cụ hay nhãn phương pháp không tự xác định chất lượng kiểm thử.

### 2.2. Coverage và số lượt chạy có ý nghĩa đến đâu?

Coverage cho biết những phần thực thi mà phương pháp đo đã quan sát, chẳng hạn edge hoặc branch trong phạm vi instrumentation. Nó không chứng minh mọi giá trị, mọi trạng thái hoặc mọi điều kiện bảo mật trên các đường đó đã được kiểm tra.

Một triệu input bị từ chối ngay tại byte đầu có thể ít hữu ích hơn một corpus nhỏ đi sâu vào các bước xác minh quyền và lưu trữ. Cần xem chất lượng đường thực thi, tỷ lệ input tới vùng quan trọng, trạng thái được khám phá và oracle được kích hoạt, không chỉ tốc độ thực thi.

Không so trực tiếp coverage trước/sau khi đổi instrumentation hoặc phạm vi target mà không nêu ngữ cảnh. Không dùng một ngưỡng coverage tùy ý làm bằng chứng duy nhất để kết luận tính năng an toàn.

## 3. Mô hình đe dọa và lựa chọn target

### 3.1. Những ranh giới phù hợp để kiểm thử

| Target | Đầu vào có thể bị điều khiển | Rủi ro và bằng chứng cần tìm |
|---|---|---|
| Parser/decoder | Bytes, độ dài, nesting, encoding và trường lặp | Crash, sai diễn giải, tiêu thụ tài nguyên hoặc chấp nhận cấu trúc bị cấm |
| Bộ xử lý tệp/archive | Metadata, đường dẫn, số mục, kích thước giải nén | Vượt phạm vi lưu trữ, xử lý dở hoặc vượt ngân sách |
| API/service | Request, ID đối tượng, trường bổ sung, header theo giao thức | Vượt quyền, trộn tenant, lỗi có tác động phụ |
| Workflow/job | Thứ tự tạo/sửa/thu hồi/xóa/retry | Trạng thái không hợp lệ, replay, tác động lặp hoặc dùng quyền cũ |
| Adapter/thư viện native | Dữ liệu từ runtime quản lý sang native | Lỗi bộ nhớ, sai hợp đồng và hành vi phụ thuộc platform |
| Cấu hình/protocol handler | Giá trị cấu hình hoặc thông điệp từ bên khác | Fallback ngoài chính sách, trạng thái parser khác nhau hoặc mở quyền |

Chọn target dựa trên khả năng tiếp cận của đầu vào và hậu quả, không chỉ hàm dễ gọi nhất. Một parser thuần là target tốt để chạy nhanh, nhưng cần một target service khác nếu yêu cầu nằm ở quyết định quyền hoặc tác động tới dữ liệu.

### 3.2. Các rủi ro của sản phẩm và của chính chiến dịch

| Mã | Kịch bản | Điều cần kiểm soát |
|---|---|---|
| R1 | Đầu vào bất thường làm crash, sai diễn giải hoặc vượt tài nguyên | Oracle parser/tài nguyên và kiểm tra biên |
| R2 | Hành vi sai quyền hoặc trạng thái vẫn thành công, không gây crash | Oracle nghiệp vụ/bảo mật và mô hình có thẩm quyền |
| R3 | Harness bỏ kiểm soát thật hoặc bắt mọi lỗi rồi coi là bình thường | Tính trung thực của target, xử lý lỗi hẹp và test sức khỏe harness |
| R4 | Trạng thái rò giữa input, dependency ngoài hoặc timing gây kết quả không tái hiện | Reset, cô lập, fixture và ghi đủ điều kiện thực thi |
| R5 | Corpus/coverage yếu tạo cảm giác kiểm thử sâu dù chỉ chạm đường từ chối | Seed, mutation có cấu trúc và metric theo đường quan trọng |
| R6 | Crash artifact/corpus chứa secret hoặc fuzzer gọi nhầm dịch vụ thật | Dữ liệu tổng hợp, quyền tối thiểu và giới hạn egress |
| R7 | Campaign lỗi/bị ngắt hoặc finding chưa xử lý vẫn được báo sạch | Gate, trạng thái kết quả, triage và bằng chứng revision |

### 3.3. Phạm vi và giới hạn phải được chốt

Mỗi target cần có owner, entry point, định dạng, giả định, dependency, revision/artifact, platform và phần không được kiểm thử. Target parser không được báo như thể đã fuzz toàn bộ xác thực, mạng, storage và concurrency của hệ thống.

Không gọi production hoặc dùng credential thật để tìm dữ liệu lỗi. Tính năng có thể gửi email, webhook, thanh toán hoặc ghi dữ liệu phải đi qua fixture/cơ chế cách ly được kiểm soát. Tắt tác động phụ ở biên ngoài có thể cần thiết, nhưng không được thay luôn quyết định quyền bằng một mock luôn cho phép rồi tuyên bố đã kiểm chứng phân quyền.

## 4. Chuyển yêu cầu bảo mật thành oracle

### 4.1. Một oracle cần có điểm quan sát

| Loại oracle | Thuộc tính cần kiểm tra | Điểm quan sát phù hợp |
|---|---|---|
| Crash/exception | Không có lỗi nội bộ bất ngờ đối với dữ liệu trong phạm vi | Exception không thuộc hợp đồng, exit status và dấu vết crash |
| Bộ nhớ | Không có lỗi bộ nhớ theo cơ chế phát hiện phù hợp | Runtime kiểm tra bộ nhớ/instrumentation ở phần native nếu áp dụng |
| Thời gian/tài nguyên | Input không vượt ngân sách đã đặc tả mà không có xử lý giới hạn | Supervisor, CPU/RAM, bộ đếm byte và kết quả hủy |
| Phân quyền | Chủ thể chỉ đọc/ghi/thực hiện hành động được cấp | Quyết định độc lập, storage/signer/event sink và trạng thái dữ liệu |
| Toàn vẹn/trạng thái | Từ chối không tạo dữ liệu dở; retry không nhân đôi tác động ngoài hợp đồng | Snapshot, event/outbox, job và khóa idempotency |
| Rò dữ liệu | Response/lỗi/log không chứa dữ liệu ngoài quyền hoặc secret fixture | Các đầu ra trong phạm vi, kể cả log/trace và artifact lỗi |
| Quan hệ ngữ nghĩa | Serialize–parse giữ ý nghĩa hoặc hai cách xử lý nhất quán theo hợp đồng | Model so sánh ngữ nghĩa, không nhất thiết bằng bytes |

Oracle phải tách kết quả từ chối hợp lệ khỏi lỗi nội bộ. Một exception được định nghĩa rõ cho input sai có thể là hành vi đúng. Crash hoặc timeout cũng chưa tự xác nhận lỗ hổng exploitable; nó là tín hiệu cần triage theo khả năng tiếp cận, tác động và giới hạn của sản phẩm.

### 4.2. Ví dụ hợp đồng cho nhập báo cáo

Hồ sơ minh họa sử dụng các yêu cầu sau; các số là tham số thiết kế của ví dụ, không phải chuẩn chung:

| ID | Yêu cầu và ranh giới đo |
|---|---|
| REP-FZ-01 | Body đầu vào tối đa 256 KiB tính theo bytes; vượt ngưỡng phải bị từ chối trước xử lý không giới hạn. |
| REP-FZ-02 | JSON phải đúng schema, không có field lạ hoặc key lặp; độ sâu container tối đa 32, root object/array tính là độ sâu 1. |
| REP-FZ-03 | Số item tối đa 1.000; trường số và kiểu dữ liệu theo schema, không tự chấp nhận giá trị ngoài miền bằng ép kiểu. |
| REP-FZ-04 | Chỉ principal được cấp quyền mới dùng report tương ứng; tenant lấy từ context xác thực, không từ dữ liệu tự khai trong body. |
| REP-FZ-05 | Input bị từ chối không tạo report dùng được, không cấp link và không phát sự kiện nghiệp vụ thành công. |
| REP-FZ-06 | Response/lỗi/log không lộ secret hoặc dữ liệu của principal/tenant khác. |

Nếu sản phẩm nhận định dạng nén, cần thêm giới hạn dữ liệu sau giải nén, số mục và đường dẫn theo hợp đồng. Ví dụ có thể đặt 2 MiB sau giải nén, nhưng giới hạn đó phải được kiểm tra ở decoder tương ứng; target JSON không giải nén không thể chứng minh nó.

### 4.3. Differential và metamorphic oracle

So sánh hai parser hoặc hai version có thể tìm khác biệt, nhưng một bên không tự là chuẩn đúng. Cần xác định hành vi chuẩn và những khác biệt được phép, chẳng hạn cách báo lỗi hoặc thứ tự trường đầu ra. Một parser cũ chấp nhận dữ liệu sai không phải lý do buộc parser mới giữ lỗi đó.

Với round-trip, có thể yêu cầu `parse(serialize(model))` giữ đúng ý nghĩa của model trong miền hợp lệ. Không yêu cầu bytes phải giống nhau nếu định dạng cho phép biểu diễn khác. Các thuộc tính này hỗ trợ tìm lỗi, không thay oracle phân quyền hay chứng minh mọi chuẩn hóa đều an toàn trong mọi ngữ cảnh.

## 5. Thiết kế harness đáng tin cậy

### 5.1. Harness là một phần của hệ thống kiểm chứng

**Harness** chuyển input do fuzzer tạo thành lời gọi target, thiết lập môi trường, kiểm tra oracle và xuất bằng chứng khi lỗi. Nó cần đủ nhỏ để hiểu nhưng vẫn giữ các điều kiện mà sản phẩm dùng thật: parser, kiểm tra giới hạn, chính sách quyền và sink liên quan trong phạm vi.

Không bỏ kiểm tra quyền để tăng số lượt thực thi rồi báo kết quả cho yêu cầu quyền. Không bắt toàn bộ exception hoặc `Throwable` và trả thành “invalid input”, vì assertion failure, lỗi nội bộ hoặc lỗi tài nguyên có thể bị che. Chỉ phân loại lỗi từ chối đã được hợp đồng xác định; lỗi ngoài danh sách phải thành tín hiệu.

### 5.2. Pseudocode cho target parser

```text
fuzz_report_parser(input_bytes):
    fixture = fresh_pure_parser_fixture()
    try:
        before = snapshot_observable_side_effects(fixture)
        try:
            result = production_report_parser.parse_with_limits(
                input_bytes,
                max_input_bytes=256KiB,
                max_container_depth=32,
                max_items=1000,
                reject_unknown_and_duplicate_fields=true
            )
            outcome = ACCEPTED(result)
        catch DeclaredInvalidReport:
            outcome = REJECTED

        assert no_unauthorized_io_or_side_effect(before, fixture)
        if outcome is ACCEPTED:
            assert schema_and_numeric_invariants_hold(result)
            assert result.item_count <= 1000
            assert semantic_round_trip_holds_for_valid_model(result)
    finally:
        release_fixture_resources(fixture)
```

Các hàm và tùy chọn mô tả trách nhiệm, không phải API chuẩn đã tự cung cấp bảo đảm. Parser thực phải có khả năng cưỡng chế giới hạn tương ứng; không chỉ ghi tham số trong harness rồi giả định thư viện sẽ thực hiện. Cleanup cần nằm trong cơ chế bảo đảm chạy khi kết thúc case bình thường/lỗi; crash cả process phải do supervisor và môi trường cô lập xử lý.

Catch hẹp giúp không che assertion hoặc lỗi nội bộ. Tính hợp lệ của `DeclaredInvalidReport` cũng cần được kiểm tra: một wrapper đổi mọi lỗi thành kiểu này sẽ làm mất tín hiệu dù harness nhìn có vẻ đúng.

### 5.3. Target có trạng thái cần mô hình độc lập

Với service báo cáo, harness có thể chọn principal A/B từ danh tính fixture được xác thực, tạo report, cấp/thu hồi quyền, đọc, xóa và retry. Nó không tự tạo một context “trusted” tùy ý để bỏ qua toàn bộ lớp xác thực nếu phạm vi đang kiểm tra lớp đó.

Một mô hình tham chiếu giữ trạng thái quyền và report theo quy tắc được phê duyệt; sau mỗi hành động, so sánh response và tác động thực với kết quả được phép. Không lấy chính hàm phân quyền của target làm oracle duy nhất, vì cùng một lỗi có thể xuất hiện ở cả phép thực thi lẫn phép kiểm tra.

Ví dụ chuỗi tuần tự: tạo report của A → B thử đọc → A cấp quyền cho B → B đọc → A thu hồi → B thử đọc lại. Hợp đồng ví dụ yêu cầu thao tác mới sau khi commit thu hồi phải bị từ chối. Nếu sản phẩm có lease/link còn hiệu lực, oracle phải mô tả chính xác cửa sổ được chấp nhận thay vì áp một giả định khác.

Fuzz chuỗi tuần tự không tự kiểm chứng race. Để xét TOCTOU hoặc thứ tự xen kẽ, cần target và cơ chế điều khiển lịch/điểm đồng bộ phù hợp, ghi được chuỗi điều kiện thực thi và oracle về thời điểm quyết định quyền.

### 5.4. Reset và tính lặp lại

Mỗi case cần trạng thái ban đầu được xác định: dữ liệu fixture, cache, biến toàn cục, thời gian, seed phụ và tài nguyên tạm. Rò trạng thái giữa input có thể tạo false positive hoặc làm một lỗi biến mất khi chạy riêng.

Nếu tái sử dụng process để tăng tốc, phải kiểm tra cơ chế reset và có bài kiểm tra trạng thái/tài nguyên qua nhiều lượt. Cô lập mỗi case trong process mới giúp hạn chế nhiễm trạng thái nhưng có thể che một loại leak chỉ xuất hiện khi process sống lâu; hai cách cần được chọn theo mục tiêu, không mặc định tương đương.

## 6. Corpus, dictionary và chiến lược mutation

### 6.1. Seed để đi sâu và seed để thử điều kiện lỗi

Corpus ban đầu nên có dữ liệu hợp lệ nhỏ/lớn, các biến thể schema/feature trong phạm vi và dữ liệu sai ở các ranh giới quan trọng. Với ví dụ báo cáo, cần seed gần giới hạn bytes, depth 31/32/33, item 999/1.000/1.001, encoding sai, key lặp, kiểu số sai và các ID report fixture khác quyền.

Giới hạn sinh input của harness phải cho phép chạm phía vượt giới hạn sản phẩm. Chẳng hạn, generator có thể cho tới 512 KiB để thử body vượt 256 KiB; nếu harness cắt mọi input về 256 KiB trước khi gọi target, nó chưa kiểm chứng việc sản phẩm từ chối dữ liệu quá cỡ.

Input đúng kích thước vẫn cần đúng schema/ngữ nghĩa để kiểm tra đường hợp lệ. Một seed dài đúng 256 KiB nhưng sai cú pháp không chứng minh hệ thống chấp nhận được tài liệu hợp lệ chạm ngưỡng.

### 6.2. Giữ cấu trúc và phá đúng ràng buộc

Dictionary có thể chứa tên field, token định dạng và các giá trị biên do hợp đồng xác định. Mutation có cấu trúc giữ các phần cần thiết để đi tới logic sâu, đồng thời thay một thuộc tính như số mục, quan hệ độ dài, ID hoặc thứ tự hành động.

Không chỉ tạo dữ liệu hợp lệ: cần cả trường lạ, dữ liệu dư, định dạng không hoàn chỉnh và tổ hợp feature. Cũng không chỉ phá toàn bộ định dạng: cần đủ case đi vào quyết định quyền, lưu trữ và trạng thái để oracle ở đó có cơ hội phát hiện lỗi.

### 6.3. Quản lý corpus như một artifact nhạy cảm

Seed nên là dữ liệu tổng hợp, có owner, version và phạm vi. Corpus có thể chứa chuỗi giống mã, tài liệu lỗi hoặc thông tin được giữ trong crash; không mở hoặc thực thi tùy tiện bằng công cụ có quyền cao.

Giảm corpus có thể giữ những case bổ sung coverage, nhưng reproducer bảo mật đã được xác minh cần lưu như regression theo hợp đồng, kể cả khi không thêm edge mới. Không xóa một bài test quyền chỉ vì coverage trùng với seed khác.

Khi chia sẻ corpus/crash, cần kiểm tra quyền truy cập, che dữ liệu và tránh đưa secret hoặc dữ liệu khách hàng thật ra ngoài kênh đã cấp quyền. Cách che dữ liệu phải giữ được điều kiện tái hiện hoặc ghi rõ hạn chế nếu không thể có cả hai trong một bản chia sẻ.

## 7. Ngân sách tài nguyên và môi trường thực thi

### 7.1. Phân biệt giới hạn sản phẩm với giới hạn chiến dịch

Giới hạn 256 KiB hoặc depth 32 thuộc hợp đồng xử lý input của ví dụ. Giới hạn RAM của worker, thời gian watchdog và tổng thời gian campaign thuộc cơ chế vận hành kiểm thử. Một worker bị giới hạn tài nguyên không tự chứng minh sản phẩm đã từ chối input đúng cách.

Hồ sơ tham chiếu đặt các tham số minh họa:

| Thuộc tính | Giá trị và cách hiểu |
|---|---|
| Kích thước input fuzzer có thể tạo | Tối đa 512 KiB để chạm cả phía vượt giới hạn body 256 KiB của sản phẩm |
| Chuỗi stateful | Tối đa 32 hành động mỗi case; mỗi hành động và payload có giới hạn riêng |
| Watchdog mỗi case | Quá 1 giây elapsed được ghi timeout cần triage; supervisor dừng worker chậm nhất ở mốc 2 giây từ bắt đầu case |
| RAM mỗi worker | Tối đa 512 MiB theo giới hạn process/cgroup hoặc cơ chế tương đương; không đồng nhất với một giới hạn heap riêng |
| Egress | Chỉ fixture và dịch vụ kiểm thử có thẩm quyền; không có đường tới production |
| PR ảnh hưởng target | Chạy toàn bộ corpus/regression bắt buộc và campaign khám phá 10 phút cho target liên quan |
| Campaign định kỳ | 2 giờ cho mỗi target quan trọng theo lịch vận hành, có owner xử lý kết quả |

Các số không phải mặc định phù hợp cho mọi parser hoặc máy CI. Cần chọn theo hợp đồng và năng lực runner, đo rõ CPU/wall time, bộ nhớ toàn process, disk tạm và số worker. Không tăng hạn tùy ý chỉ để làm một timeout biến mất mà chưa hiểu nguyên nhân.

Campaign 10 phút không đồng nghĩa đã kiểm tra mọi input. Corpus bắt buộc phải hoàn thành, engine phải có trạng thái sức khỏe hợp lệ và mọi tín hiệu lỗi phải được xử lý theo gate. Một run bị hủy vì hạ tầng trước khi đạt điều kiện không được báo như run hoàn tất không có finding.

### 7.2. Supervisor và dọn tài nguyên

Watchdog phải quan sát phần có thể treo, không chỉ thread đợi kết quả. Hủy một future không tự bảo đảm parser native hoặc tiến trình con đã dừng. Cần cơ chế terminate/cách ly có kiểm chứng và dọn process con, file tạm, socket, dữ liệu fixture cùng slot runner.

Khi case vượt RAM, timeout hoặc bị signal, giữ kết quả riêng và metadata đủ triage. Phân biệt input khiến sản phẩm tăng tài nguyên không giới hạn với runner thiếu dung lượng, fixture mạng hỏng hoặc deadline không phù hợp. Cả hai có thể làm run không đạt, nhưng nguyên nhân và cách sửa khác nhau.

Không cấp quyền quản trị host, mount secret production hoặc quyền ký/phát hành cho worker fuzz chỉ vì nó chạy trong CI. Input sinh ra có thể điều khiển parser, filesystem hoặc network path; chính môi trường kiểm thử phải giới hạn hậu quả khi target có lỗi.

### 7.3. Tín hiệu sức khỏe của engine

Ghi target đã nạp, corpus đã chạy, số case hoàn thành, thời gian, trạng thái watchdog, coverage feedback nếu dùng và oracle nào hoạt động. Target không được gọi, corpus không tải được hoặc instrumentation mất tín hiệu phải thành lỗi cấu hình/chiến dịch.

Đối với coverage-guided, cần một seed sức khỏe có đường thực thi đã biết và bằng chứng engine nhận được feedback tương ứng. Không kết luận fuzzer hiệu quả chỉ vì process còn sống và in counter tăng. Một engine chạy toàn input vào stub hoặc vào wrapper luôn từ chối có thể không kiểm tra target cần bảo vệ.

## 8. Tái hiện, giảm mẫu lỗi và triage

### 8.1. Một finding cần giữ những gì?

Record tối thiểu cần có target/oracle, input hoặc chuỗi thao tác gốc, tham chiếu artifact lỗi được bảo vệ, revision và artifact digest, harness/corpus/configuration, platform/runtime, cách build/instrument, giới hạn và điều kiện fixture. Với stateful/concurrency, cần trạng thái ban đầu, clock/seed phụ và lịch thực thi quan trọng nếu có.

Seed ngẫu nhiên của engine một mình thường không đủ để đảm bảo tái hiện khi engine, corpus, lịch thread hoặc môi trường thay đổi. Cần giữ chính input/sequence và điều kiện gọi target. Digest input giúp định danh, nhưng không thay nội dung reproducer khi cần chạy lại.

Crash artifact có thể chứa raw bytes, stack trace, memory dump hoặc dữ liệu fixture. Đặt quyền truy cập và giới hạn lưu thích hợp; không in nguyên input vào log công khai. Khi cần chia sẻ, dùng bản đã được phép và giữ record về quan hệ với bản gốc.

### 8.2. Reproduce và minimize

```text
triage_fuzz_signal(signal):
    preserve_original_case_and_execution_context(signal)
    replay = run_reproducer_on_matching_target(signal)
    classify_product_bug_harness_bug_or_environment_issue(replay)

    if signal_is_confirmed:
        minimal = reduce_input_or_sequence_preserving_relevant_oracle(signal)
        verify_original_and_minimal_cases(signal, minimal)
        record_impact_reachability_and_owner()
        add_required_regression_with_expected_behavior()
```

Các hàm mô tả trách nhiệm. Giảm mẫu cần giữ điều kiện lỗi và oracle liên quan; với chuỗi thao tác, xóa bước tạo/quyền có thể làm lỗi khác xuất hiện thay cho lỗi gốc. Lưu cả bản gốc và bản nhỏ cùng bằng chứng, không ghi đè bản gốc ngay khi có input ngắn hơn.

Grouping theo stack trace hoặc thông tin lỗi giúp điều phối nhưng không chứng minh cùng nguyên nhân. Hai lỗi khác nhau có thể cùng crash ở một hàm, và cùng một lỗi có thể tạo nhiều stack trace. Quyết định gộp cần được kiểm tra để không làm mất phạm vi tác động.

### 8.3. Đánh giá bảo mật và xác minh sửa

Triage cần xác định input có đến được từ bên không tin cậy không, quyền target có gì, tác động tới dữ liệu/tài nguyên và kiểm soát nào còn hạn chế. Không gọi mọi exception là lỗ hổng, cũng không bỏ qua một lỗi phân quyền chỉ vì không crash.

Trong hồ sơ ví dụ, finding bảo mật đã xác nhận và unexpected crash/hang chưa phân loại ở target nhạy cảm chặn release mới liên quan cho đến khi có disposition theo policy. Tín hiệu được tiếp nhận cần triage trong 24 giờ; dấu hiệu ảnh hưởng thực tế hoặc lộ dữ liệu kích hoạt quy trình sự cố phù hợp ngay, không chờ hết hạn.

Bản sửa phải làm reproducer/regression đạt đúng hành vi, giữ đường hợp lệ và chạy lại fuzz target liên quan. Không chỉ thêm một điều kiện nhận diện chính bytes gây crash trong khi nguyên nhân tổng quát vẫn còn. Nếu dùng ngoại lệ cho rủi ro mà policy cho phép, hồ sơ ví dụ giới hạn tối đa 7 ngày, có owner và không tự gia hạn; ngoại lệ không biến lỗi thành không tồn tại.

## 9. Tích hợp vào CI và vòng đời phát triển

### 9.1. Các lớp chạy bổ sung cho nhau

Regression nhỏ đã xác minh nên chạy sớm và ổn định. Campaign ngắn trên PR tập trung các target bị ảnh hưởng; campaign dài giúp mở rộng khám phá ở các target quan trọng. Ngân sách dài hơn không bù được oracle sai hoặc harness không gọi code thật.

```text
fuzz_gate(candidate):
    targets = affected_and_required_targets(candidate, trusted_policy)
    for target in targets:
        verify_harness_fixture_and_feedback_health(target)
        require required_corpus_and_regressions_pass(target, candidate)
        campaign = run_bounded_discovery(target, candidate, approved_budget)
        require campaign.completed_with_valid_health
        require no_unresolved_blocking_signal_or_finding(campaign, target)

    bind_results_to_candidate_harness_config_and_corpus()
    authorize_gate_result_for_exact_candidate()
```

Policy chọn target và điều kiện pass phải đến từ nguồn có thẩm quyền. Không để một PR bỏ target khó, bắt mọi lỗi hoặc giảm budget rồi tự cấp kết quả đạt cho chính thay đổi đó. Thay harness/oracle/corpus bắt buộc có thể ảnh hưởng trực tiếp chất lượng bằng chứng và cần review phù hợp.

### 9.2. Revision và trạng thái run

Báo cáo cần gắn source revision/artifact, harness, dependency/runtime, platform, corpus và cấu hình engine. Kết quả của commit trước, platform khác hoặc oracle đã thay không tự áp dụng cho candidate hiện tại.

Phân biệt ít nhất: hoàn tất đạt điều kiện, có finding chặn, lỗi hạ tầng/harness, bị ngắt và chưa đủ dữ liệu. Run bị cancel không được đổi thành success chỉ vì chưa lưu crash. Campaign kết thúc đúng budget có thể được ghi hoàn tất theo hợp đồng; nó vẫn chỉ là kết luận cho thời gian và phạm vi đã chạy.

### 9.3. Duy trì target sau khi sửa lỗi

Khi đổi schema, parser, thư viện native, cơ chế quyền hoặc workflow, cập nhật corpus/model và kiểm tra lại giả định. Reproducer cũ có thể cần adapter để giữ nghĩa nghiệp vụ, nhưng không được xóa vì làm build đỏ mà không có quyết định có căn cứ.

Theo dõi target không còn được gọi, coverage feedback mất, số input đi sâu giảm mạnh và finding lặp lại. Metric cần hỗ trợ tìm khoảng trống chứ không tạo mục tiêu tăng số lượt chạy bằng cách bỏ kiểm tra hoặc bỏ side-effect oracle.

## 10. Ma trận yêu cầu bảo mật có thể kiểm chứng

Các yêu cầu sau thuộc hồ sơ minh họa. Owner tính năng chịu trách nhiệm bất biến sản phẩm; nhóm kiểm thử/nền tảng chịu trách nhiệm harness/runner/gate; bên an toàn hỗ trợ đánh giá tác động và ngoại lệ. Khi áp dụng cần gán chủ thể và giá trị phù hợp với hệ thống.

| ID / rủi ro | Yêu cầu | Điểm cưỡng chế | Bằng chứng chấp nhận |
|---|---|---|---|
| FZ-01 / R1, R2 | Target phải có owner, phạm vi, entry point, yêu cầu/oracle và phần không được kiểm thử; parser và service không được báo như cùng phạm vi. | Hồ sơ target và review | AC-01: xác định đúng lớp được kiểm tra, gồm các đường trạng thái quan trọng. |
| FZ-02 / R2 | Oracle phải phát hiện vi phạm quyền/toàn vẹn/tài nguyên liên quan, không chỉ crash hoặc response code. | Model, assertion và sink quan sát | AC-02: fixture trả thành công ngoài quyền hoặc tạo tác động trước lỗi phải bị phát hiện. |
| FZ-03 / R3 | Harness phải gọi kiểm soát thực trong phạm vi, catch lỗi hẹp và không che assertion/lỗi nội bộ. | Harness và bài kiểm tra sức khỏe | AC-03: fault fixture ngoài hợp đồng không bị đổi thành input từ chối hợp lệ. |
| FZ-04 / R4 | Case phải có reset/trạng thái đầu xác định và giữ đủ điều kiện tái hiện, kể cả sequence/clock/schedule khi liên quan. | Fixture, supervisor và reproducer | AC-04: chạy riêng và xen kẽ case tái hiện đúng; rò trạng thái được phát hiện. |
| FZ-05 / R1, R5 | Corpus/mutation phải chạm đường hợp lệ, ngữ nghĩa và biên vượt giới hạn; không cắt bỏ input trước kiểm soát cần thử. | Corpus, generator và review | AC-05: bytes/depth/item ở hai phía ngưỡng tới đúng target và oracle. |
| FZ-06 / R4, R6 | Runner phải giới hạn RAM/thời gian/egress, dừng worker quá hạn và dọn tài nguyên; không có quyền production không cần thiết. | Sandbox và supervisor | AC-06: fixture treo/quá RAM hoặc gọi đích cấm không ảnh hưởng ngoài phạm vi, kết quả được phân loại đúng. |
| FZ-07 / R3, R5 | Instrumentation/feedback và việc target được gọi phải có kiểm tra sức khỏe; mất tín hiệu không được coi là run sạch. | Engine health và gate | AC-07: target stub hoặc feedback lỗi làm campaign chưa đạt điều kiện. |
| FZ-08 / R4, R7 | Finding phải giữ input gốc/context, có triage, minimize bảo toàn lỗi và owner; không gộp chỉ theo stack. | Kho reproducer và quy trình triage | AC-08: bản gốc/bản nhỏ đều tái hiện oracle liên quan và đủ metadata. |
| FZ-09 / R1, R2, R7 | Sửa lỗi phải có regression theo yêu cầu, đường hợp lệ và fuzz lại target; kết quả gắn đúng revision/config/platform. | CI regression và fuzz | AC-09: reproducer fail ở bản lỗi, đạt ở bản sửa và không còn vi phạm cùng bất biến trong bằng chứng yêu cầu. |
| FZ-10 / R7 | PR liên quan chạy corpus/regression bắt buộc và campaign 10 phút; campaign định kỳ 2 giờ theo hồ sơ; bị ngắt/lỗi không thành success. | CI/gate và lịch vận hành | AC-10: thiếu corpus, run bị ngắt hoặc finding chặn không cho gate đạt. |
| FZ-11 / R6 | Corpus/crash/log phải có quyền truy cập, dữ liệu tổng hợp và che secret; không phát raw input/dump sang kênh ngoài quyền. | Artifact store, log và egress | AC-11: marker nhạy cảm fixture được bảo vệ và reproducer vẫn quản lý được. |
| FZ-12 / R7 | Tín hiệu được triage trong 24 giờ; finding chặn không bị bỏ qua; ngoại lệ được phép tối đa 7 ngày, đúng phạm vi, không tự gia hạn. | Quản lý finding/ngoại lệ và gate | AC-12: deadline, disposition và expiry được cưỡng chế/quan sát đúng. |

## 11. Test và acceptance criteria

### 11.1. Cách kiểm chứng cơ chế fuzzing

Dùng target và fault fixture vô hại, dữ liệu tổng hợp, principal thử và sink có bộ đếm. Một số ca chủ động cấy lỗi vào fixture để kiểm tra harness/oracle có báo lỗi hay không; đó là kiểm tra sức khỏe cơ chế, không phải thay target production bằng mock rồi kết luận sản phẩm an toàn.

Mọi mốc thời gian cần điểm bắt đầu/kết thúc và sai số đo được chấp thuận; dùng đồng hồ kiểm soát khi thử expiry. Kết quả cần quan sát ở target, state/sink, supervisor và gate, không chỉ dòng cuối stdout.

### 11.2. Các ca nghiệm thu

**AC-01 — Target và phạm vi, truy vết FZ-01.**

Tạo target parser, target service và target chuỗi thao tác cho ví dụ. Hồ sơ phải chỉ rõ REP-FZ nào được kiểm tra ở đâu và dependency nào còn ngoài phạm vi. Một báo cáo chỉ chạy parser không được đánh dấu REP-FZ-04 về quyền đã đạt. Đối chứng có owner, revision và oracle hoạt động cho từng target được tuyên bố.

**AC-02 — Oracle ngoài crash, truy vết FZ-02.**

Cho fixture có lỗi trả report của B cho A mà không throw exception, rồi một biến thể trả lỗi sau khi đã gọi signer/phát sự kiện. Oracle phải phát hiện cả dữ liệu ngoài quyền và tác động phụ trái REP-FZ-04/05. Sau khi sửa fixture theo mô hình, ca hợp lệ vẫn thành công và các ca ngoài quyền không tạo tác động bị cấm.

**AC-03 — Catch và tính trung thực của harness, truy vết FZ-03.**

Phát sinh lỗi định dạng được khai báo, một lỗi nội bộ ngoài hợp đồng và một assertion failure trong fixture. Chỉ lỗi định dạng hợp lệ được phân loại từ chối; hai lỗi còn lại phải trở thành tín hiệu. Thử wrapper cố tình đổi mọi lỗi thành lỗi từ chối hoặc thay kiểm tra quyền bằng always-allow; bài kiểm tra sức khỏe/review phải phát hiện và không cho kết quả đó làm bằng chứng bảo mật.

**AC-04 — Reset và reproducer, truy vết FZ-04.**

Chạy case X riêng, chạy Y rồi X và chạy lại X với fixture sạch. Trạng thái ban đầu và oracle phải nhất quán theo hợp đồng; leak cache/quyền từ Y không được che lỗi của X. Với stateful case, giữ đủ chuỗi tạo/cấp/thu hồi/đọc; với target có lịch điều khiển, tái lập cả clock/schedule liên quan. Một seed engine không có input/context không được coi là hồ sơ reproducer đầy đủ.

**AC-05 — Biên và khả năng đi sâu, truy vết FZ-05.**

Đưa tài liệu hợp lệ được dựng đúng ở độ dài `256 KiB - 1`, `256 KiB` và biến thể vượt `256 KiB + 1`; hai trường hợp trong ngưỡng không bị từ chối chỉ vì chạm hạn, còn trường hợp vượt bị chặn theo hợp đồng. Thử depth 31/32/33, item 999/1.000/1.001, key lặp, field lạ và encoding/kiểu số sai. Quan sát target nhận bytes thực, không phải dữ liệu đã bị harness cắt. Corpus phải có case tới được logic sâu thay vì tất cả dừng ở kiểm tra byte đầu.

**AC-06 — Tài nguyên và cô lập, truy vết FZ-06.**

Cho fixture treo, tiêu thụ RAM có kiểm soát và thử kết nối tới đích fixture bị cấm. Quá 1 giây phải có tín hiệu timeout; worker bị dừng chậm nhất ở mốc 2 giây theo hồ sơ, RAM nằm trong cơ chế giới hạn 512 MiB và egress ngoài quyền bị chặn. Kiểm tra process con, file tạm và slot sau dừng. Không dùng việc worker bị kill làm bằng chứng rằng target đã trả một lỗi giới hạn hợp lệ.

**AC-07 — Feedback và target health, truy vết FZ-07.**

Chạy seed sức khỏe qua target đã biết có tín hiệu thực thi; engine phải ghi được target/coverage feedback phù hợp nếu dùng coverage-guided. Tắt instrumentation, đổi entry point thành stub hoặc làm corpus không tải được; campaign phải ở trạng thái lỗi/chưa đủ điều kiện. Counter tăng ở wrapper không đủ thay bằng chứng code cần kiểm tra đã được gọi.

**AC-08 — Triage và giảm mẫu, truy vết FZ-08.**

Tạo một finding fixture có input dài hoặc chuỗi nhiều bước. Giữ bản gốc, metadata rồi giảm mẫu; cả bản gốc và bản nhỏ phải tái hiện vi phạm liên quan trên đúng target. Nếu bản nhỏ chỉ tạo lỗi setup khác, không được dùng thay nguyên nhân ban đầu. Tạo hai fault cùng stack để xác nhận grouping không tự đóng một finding chưa được phân tích.

**AC-09 — Regression và bản sửa, truy vết FZ-09.**

Reproducer đã xác minh phải fail oracle ở bản lỗi và đạt hành vi mong đợi ở candidate sửa. Chạy các ca hợp lệ, biên và target liên quan theo hồ sơ; bản sửa chỉ chặn một chuỗi bytes mà biến thể cùng lỗi vẫn vi phạm thì chưa đạt. Thử dùng báo cáo của revision/platform hoặc harness cũ không phù hợp; gate không được tự nhận là bằng chứng candidate mới.

**AC-10 — Gate và run chưa hoàn tất, truy vết FZ-10.**

Chạy corpus/regression bắt buộc và campaign PR theo ngân sách 10 phút; xác nhận campaign định kỳ được điều phối đúng hồ sơ 2 giờ và có owner. Chủ động hủy run, làm worker lỗi hạ tầng, bỏ một regression bắt buộc hoặc giữ finding chặn chưa xử lý; không trường hợp nào thành success chỉ vì chưa lưu crash mới. Kết thúc khám phá đúng budget với health hợp lệ và đủ điều kiện được phân biệt với run bị ngắt.

**AC-11 — Artifact nhạy cảm, truy vết FZ-11.**

Dùng marker secret fixture trong một crash artifact được kiểm soát. Raw bytes/dump không được phát sang stdout, comment hoặc kho ngoài quyền; principal không có quyền không tải được artifact. Bản chia sẻ đã che cần giữ quan hệ với bản gốc và ghi được có còn tái hiện hay không. Kiểm tra runner không có credential production và không gọi endpoint thật ngoài phạm vi.

**AC-12 — Deadline, disposition và ngoại lệ, truy vết FZ-12.**

Ghi tín hiệu tại `t0`, đo triage trong 24 giờ và kiểm tra owner/disposition. Finding bảo mật chặn hoặc crash/hang nhạy cảm chưa phân loại không được bỏ qua bằng nhãn “fuzz flaky”. Ngoại lệ thuộc loại được policy cho phép phải đúng target/revision/rủi ro, hạn tối đa 7 ngày; sau hạn hoặc khi điều kiện đổi, gate không được tiếp tục dùng bản cũ. Tín hiệu ảnh hưởng thực tế cần được chuyển sang quy trình sự cố phù hợp.

### 11.3. Điều kiện chấp nhận và giới hạn kết luận

FZ-01–FZ-12 cần có owner, cấu hình, bằng chứng đúng target/candidate và kết quả AC-01–AC-12. Các ca ở đây là đặc tả nghiệm thu, không phải tuyên bố đã thực hiện trên một hệ thống cụ thể.

Run không tìm thấy vi phạm chỉ hỗ trợ kết luận cho phạm vi, oracle, corpus, budget và môi trường đã chạy. Nó không chứng minh không có mọi lỗi logic, side channel, race, lỗi cấu hình hoặc đầu vào chưa được khám phá. Những phần đó phải có yêu cầu và phương pháp kiểm chứng bổ sung thích hợp.

## 12. Ví dụ nối finding với vòng đời phát triển

Với bộ nhập báo cáo, nhóm chọn parser target để thử REP-FZ-01–03, service target cho REP-FZ-04–06 và một model stateful cho cấp/thu hồi quyền. Corpus gồm dữ liệu hợp lệ đi sâu và các biên đã đặc tả; runner chỉ dùng fixture và quyền kiểm thử.

Fuzzer tạo chuỗi trong đó B đọc report sau khi quyền đã bị thu hồi. Tiến trình không crash, nhưng model và bộ đếm sink phát hiện vi phạm. Nhóm giữ sequence/context, tái hiện, giảm mẫu và xác định cache quyền chưa bị vô hiệu theo hợp đồng, thay vì gộp nó vào nhóm lỗi parser.

Bản sửa cập nhật điểm quyết định quyền/cache, regression giữ chuỗi tối thiểu và test thêm ca hợp lệ, retry cùng trường hợp quyền chưa từng được cấp. CI chạy trên candidate mới, fuzz lại target liên quan và ràng buộc báo cáo với harness/corpus/configuration. Finding chỉ được đóng theo bằng chứng sửa và quy trình có thẩm quyền.

Fuzz testing đem lại giá trị khi đầu vào được khám phá gặp một oracle đúng và một quy trình xử lý có trách nhiệm. Yêu cầu bảo mật xác định điều gì không được phép xảy ra; harness và môi trường tạo điều kiện quan sát; reproducer cùng regression giữ bài học đó trong những lần phát triển tiếp theo.
