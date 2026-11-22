# Search timing leakage: rò rỉ thông tin qua thời gian tìm kiếm

## 1. Không trả tài liệu vẫn có thể hé lộ tài liệu tồn tại

Một người chỉ được xem hồ sơ của phòng mình. Khi tìm một từ khóa bí mật thuộc phòng khác, API luôn trả danh sách rỗng. Nhưng request chậm hơn rõ rệt vì backend tìm toàn bộ tenant, lấy các candidate rồi gọi kiểm tra quyền cho từng tài liệu bị ẩn.

Nếu khác biệt đó ổn định và có thể quan sát, người gọi có thể suy đoán có tài liệu khớp dù không nhận được ID, tiêu đề hay nội dung.

**Search timing leakage** là việc thông tin ngoài quyền được suy ra từ thời gian hoặc các đại lượng hiệu năng có thể quan sát của quá trình tìm kiếm.

Đây là một kênh phụ: dữ liệu không nhất thiết xuất hiện trong body, nhưng ảnh hưởng tới công việc server thực hiện và để lại dấu vết trong phản hồi.

Không phải mọi query chậm là một lỗ hổng và không phải mọi chênh lệch là bằng chứng tấn công. Cần chứng minh quan sát giúp phân biệt một trạng thái bí mật mà người gọi không được phép biết.

Trong bảo vệ logic nghiệp vụ, điều này quan trọng khi hệ thống phải che sự tồn tại của hồ sơ, khách hàng, giao dịch, dự án hoặc dữ liệu giữa các tenant/đơn vị.

## 2. Xác định bí mật và mô hình quan sát

### 2.1. Nêu rõ điều người gọi không được biết

Các câu hỏi cần làm rõ:

- Một hồ sơ có tồn tại không?
- Có tài liệu chứa từ khóa hoặc thuộc tính nhạy cảm không?
- Một khách hàng/giao dịch có thuộc một nhóm hạn chế không?
- Có thay đổi nào ở tập dữ liệu riêng tư vừa ảnh hưởng cache hoặc index không?

Nếu người gọi được phép biết một dữ kiện, việc thời gian phụ thuộc dữ kiện đó không tự là rò rỉ ngoài quyền. Scope bảo mật phải được định nghĩa trước khi đánh giá.

### 2.2. Giữ nguyên phần dữ liệu được phép khi so sánh

Một cách lập luận hữu ích là so hai trạng thái hệ thống:

```text
Giống nhau:
    actor, tenant, quyền đọc, query và dữ liệu actor được phép biết.

Khác nhau:
    một dữ kiện hoặc tài liệu bí mật ngoài quyền.

Câu hỏi:
    quan sát bên ngoài có giúp phân biệt hai trạng thái đó không?
```

So một từ phổ biến với một chuỗi ngẫu nhiên rồi thấy query khác thời gian chưa chứng minh rò rỉ. Hai từ có thể có đặc tính tìm kiếm khác nhau vì lý do bình thường.

Phép so sánh cần loại bớt các nguyên nhân công khai, không chỉ chọn hai request có kết quả khác về độ trễ.

### 2.3. Quan sát không chỉ có một số thời gian tổng

| Kênh quan sát | Ví dụ |
|---|---|
| Thời gian đầu cuối | Đến byte đầu, nhận xong response hoặc timeout |
| Header chẩn đoán | Thời gian DB/index, cache hit/miss, số bước xử lý |
| Hình dạng response | Status, độ dài, loại lỗi, cursor hoặc cờ có trang sau |
| Dữ liệu dẫn xuất | Count, facet, score, snippet hoặc gợi ý |

Nếu count đã công khai số tài liệu ẩn, đó là rò rỉ trực tiếp cần sửa, không nên chỉ tập trung làm nhiễu thời gian. Đánh giá toàn bộ quan sát, không giới hạn vào body đã bị làm rỗng.

## 3. Những cơ chế thường tạo timing leakage

### 3.1. Tìm rộng rồi lọc quyền từng candidate

```text
tìm trên tập rộng
→ nhận N candidate
→ gọi kiểm tra quyền hoặc nạp ACL cho từng candidate
→ bỏ hết item ngoài quyền
→ trả []
```

Nếu N phụ thuộc số tài liệu bí mật khớp, thời gian có thể trở thành chỉ báo về chúng. Việc xóa mọi hit trước serialize không xóa chi phí đã phát sinh.

Các vòng lặp nạp owner, group, grant hoặc tài liệu gốc riêng lẻ có thể làm khác biệt lớn hơn, nhất là khi phải gọi nguồn khác.

### 3.2. Nhánh tồn tại và không tồn tại có công việc khác nhau

Ví dụ tìm ID chính xác:

```text
không tồn tại → trả ngay
có tồn tại nhưng ngoài quyền → nạp owner, quan hệ và policy rồi trả cùng 404
```

Body giống nhau nhưng đường xử lý khác. Có thể giảm chênh lệch bằng truy vấn scoped và cấu trúc xử lý phù hợp, nhưng một query duy nhất cũng không tự bảo đảm thời gian không phụ thuộc dữ liệu.

### 3.3. Aggregate, highlight hoặc snippet vẫn chạy trên tài liệu ẩn

Engine có thể tính facet, giải thích score hoặc lấy full text trước khi ứng dụng lọc item. Dù các phần đó không được trả, công việc của chúng vẫn có thể ảnh hưởng thời gian.

Không tính dữ liệu nhạy cảm không cần thiết rồi hy vọng việc bỏ khỏi response đã giải quyết mọi kênh rò rỉ.

### 3.4. Cache và index dùng chung

Cache hit có thể nhanh hơn miss; index có thể phải xử lý posting/candidate khác nhau tùy dữ liệu. Nếu trạng thái đó tương quan với bí mật, có thể hình thành tín hiệu.

Tuy nhiên, quan sát cache nhanh/chậm chỉ trực tiếp cho biết khác biệt đường cache theo những giả định nhất định. Không tự kết luận nó chứng minh một tài liệu bí mật cụ thể tồn tại; cần kiểm tra chuỗi suy luận và các nguyên nhân thay thế.

### 3.5. Lọc logic đúng chưa chứng minh chi phí độc lập

Predicate tenant/ACL có thể đúng về kết quả, trong khi query plan, index thống kê hoặc shared resource vẫn làm lượng công việc thay đổi theo dữ liệu ngoài quyền.

Do đó, không thể chứng minh chống timing leakage chỉ bằng việc nhìn thấy `tenant_id` trong SQL hoặc một filter trong request gửi tới engine. Cần xem cách thực thi và quan sát thực tế theo mô hình đe dọa.

## 4. Bắt đầu từ authorization và quyền tìm theo field

### 4.1. Scope là dữ liệu server quyết định

Actor, tenant, phạm vi owner/phòng ban và grant phải đến từ nguồn có thẩm quyền. Filter người dùng chỉ thu hẹp phạm vi đó, không được thay thế hoặc tạo nhánh OR thoát khỏi nó.

Nếu không đánh giá được scope bắt buộc, không fallback tìm toàn bộ rồi lọc sau. Một lỗi policy không được mở rộng dữ liệu và công việc phụ thuộc tập bí mật.

### 4.2. Không cho tìm thuộc tính mà policy không cho phép suy ra

Ẩn field trong response nhưng cho lọc theo mọi giá trị của nó có thể đã tạo một oracle về thuộc tính. Timing chỉ là một trong nhiều dấu hiệu người gọi có thể quan sát.

Cần xét quyền trên field dùng để tìm, lọc, sort, facet và highlight. Có quyền xem tiêu đề không đồng nghĩa được hỏi mọi điều kiện về lương, tài khoản nhận tiền hoặc nhãn điều tra nội bộ.

### 4.3. Che sự tồn tại cần hợp đồng phản hồi nhất quán

Nếu policy yêu cầu người ngoài quyền không biết tài liệu có tồn tại, chọn cách xử lý không tìm thấy/không được đọc phù hợp, chẳng hạn một phản hồi `404` chung trong phạm vi đó.

Không trả cùng status rồi thêm tên owner, loại lỗi đặc biệt hoặc header xác nhận có tài liệu bị ẩn. Đồng thời, status/body giống nhau vẫn chưa là bằng chứng thời gian đã an toàn.

### 4.4. Không biến detector thành oracle mới

Không trả “query của bạn khớp 12 tài liệu riêng tư” hoặc chỉ yêu cầu xác thực bổ sung khi có hit bí mật, nếu bản thân điều đó bị cấm tiết lộ.

Rate limit, challenge và thông báo lỗi cũng là quan sát. Phản ứng dựa trên dữ liệu bí mật cần được đánh giá như một phần của hợp đồng, không chỉ như biện pháp phòng thủ tự động.

## 5. Giảm công việc phụ thuộc dữ liệu ngoài quyền

### 5.1. Tạo kế hoạch truy vấn trong scope ngay từ đầu

Ưu tiên áp phạm vi bắt buộc vào tập truy vấn/candidate mà engine thực sự xử lý theo khả năng hỗ trợ, thay vì lấy toàn bộ hit rồi gọi ACL N lần.

Có thể tính phạm vi actor trước, dùng quan hệ đã được biểu diễn phù hợp và batch các kiểm tra cần thiết. Tránh các nhánh không cần thiết như `existsAnywhere` trước khi kiểm tra truy cập trong scope.

Điều này giảm một nguồn tín hiệu lớn, không tự hứa mọi truy vấn scoped có thời gian cố định.

### 5.2. Minh họa Java về cấu trúc luồng

Các dependency là hợp đồng minh họa của ứng dụng, không phải API engine có sẵn.

```java
SearchResult search(UUID tenantId, SearchInput input) {
    ActorContext actor = identity.requireTenantActor(tenantId);
    SearchCriteria criteria = queryRules.validateAndBound(input);

    ReadScope scope = readScopes.requireCurrentScope(actor);
    fieldPolicy.requireAllowedSearchOperations(actor, criteria);

    ScopedSearchPlan plan = plans.build(
            scope, criteria, queryBudgets.forActor(actor));

    ScopedSearchData data = searchRepository.execute(plan);

    return presenter.toPermittedResponse(
            actor, data, criteria.requestedPublicMetadata());
}
```

Các hợp đồng cần được triển khai thật:

- `scope` không được ghi đè bởi query client.
- Repository không bỏ scope ở nhánh exact ID, count, facet hoặc fallback.
- Những field/metadata không cần hoặc không được phép không được lấy và tính vô hạn.
- Query budget không cho vòng recheck quét candidate bí mật không giới hạn.
- Presenter không trả raw timing, candidate count hoặc dữ liệu debug nhạy cảm.

Đoạn code không phải một triển khai constant-time. Kế hoạch thực thi, cache, index và việc dùng nguồn authority vẫn cần được đánh giá riêng.

### 5.3. Cân nhắc phân vùng theo ranh giới bảo mật

Index hoặc namespace tách theo tenant có thể giảm công việc chéo tenant và các phụ thuộc dữ liệu không cần thiết. Nhưng tài liệu riêng tư trong cùng tenant vẫn có thể tạo kênh rò rỉ.

Không mặc định phải có một index cho mỗi user; điều đó có chi phí và độ phức tạp lớn. Cần chọn cách phân vùng phù hợp mức isolation thực sự yêu cầu và kiểm chứng trên kiến trúc đó.

### 5.4. Kiểm tra lớp dữ liệu và đường đi thực tế

Xem query plan, candidate scan, số lần nạp ACL, request tới dependency và hoạt động tạo snippet/aggregate trong môi trường được phép quan sát.

Các số đo nội bộ giúp giải thích nguyên nhân. Chúng không nên được công khai cho mọi người gọi chỉ vì thuận tiện debug.

## 6. Metadata, cache và index cũ cần được xử lý cùng nhau

### 6.1. Metadata có thể làm tín hiệu chính xác hơn

Một header như `Server-Timing` hoặc thông tin cache/engine có thể giúp người gọi tách nhiễu mạng khỏi chi phí server. Các field như thời gian tìm trong index, số shard hoặc candidate count cần được đánh giá trước khi trả công khai.

Bỏ header chẩn đoán không loại bỏ thời gian quan sát bên ngoài, nhưng tránh cung cấp thêm chi tiết không cần thiết.

### 6.2. Count/facet đã được làm trống vẫn có thể tốn công việc bí mật

Nếu API không trả count nhưng engine vẫn tính count toàn corpus, thời gian của bước đó còn tồn tại. Cần bỏ công việc không cần thiết hoặc thực hiện đúng scope, không chỉ bỏ field response.

Autocomplete và sửa lỗi từ cũng cần nguồn được phép. Một từ điển công khai có chủ ý khác với bộ gợi ý được dựng từ tiêu đề riêng tư rồi lọc ở cuối.

### 6.3. ACL trong index là một bản sao có thể trễ

Sau thu hồi grant hoặc đổi owner, index có thể còn candidate cũ. Một recheck cuối có thể ngăn trả hit, nhưng số lượng recheck và metadata tính trước vẫn phụ thuộc dữ liệu cũ đó.

Cần mức độ mới phù hợp: đồng bộ index, kiểm tra version/watermark theo scope, chọn nguồn khác hoặc dừng khi không đủ căn cứ. Event invalidation bất đồng bộ không tự là thu hồi tức thời.

Không dùng việc đã loại hit khỏi body để tuyên bố mọi kênh quan sát của ACL cũ đã biến mất.

### 6.4. Cache phải phân vùng đúng quyền và dữ liệu

Response cache chỉ theo keyword có thể trả sai dữ liệu trực tiếp. Trước hết phải giữ scope tenant, actor/quyền field, filter và các phiên bản liên quan theo hợp đồng.

Sau đó mới đánh giá liệu thời gian hit/miss của cache dùng chung có tiết lộ một trạng thái mà policy muốn che hay không. Cache plan và cache kết quả có mục đích khác nhau; không gom mọi chênh lệch cache thành cùng một lỗi.

## 7. Vì sao sleep ngẫu nhiên không phải cách sửa đầy đủ?

### 7.1. Nhiễu thêm vào có thể bị giảm bằng nhiều quan sát

Nếu đường có tài liệu bí mật luôn làm nhiều công việc hơn, thêm một khoảng trễ ngẫu nhiên không tự xóa quan hệ đó. Người gọi có thể tổng hợp nhiều mẫu nếu còn đủ ngân sách truy vấn.

Nhiễu cũng làm chậm người dùng hợp lệ và có thể tăng thời gian giữ tài nguyên. Không dùng nó thay cho việc sửa scope, nhánh tồn tại hoặc metadata.

### 7.2. Thời gian tối thiểu không che được mọi nhánh

Một mức trễ sàn chỉ làm các request đủ nhanh chờ tới cùng mốc. Nhánh chậm hơn sàn, timeout hoặc queueing vẫn có thể khác nhau.

Nếu áp padding như một lớp bổ sung, cần biết giới hạn xử lý, cách xử lý vượt ngân sách, tác động lên đồng thời và quan sát còn lại. Không chỉ chọn một số mili giây rồi ghi “constant-time” trong tài liệu.

### 7.3. Busy wait tạo chi phí phòng thủ không cần thiết

Vòng chờ chiếm CPU có thể làm tình trạng quá tải tệ hơn. Trì hoãn bất đồng bộ cũng giữ những tài nguyên khác theo thiết kế, nên không phải chi phí bằng 0.

Đánh giá padding trong ngân sách hệ thống và threat model nếu thực sự cần. Các hàng rào loại bỏ công việc bí mật và giảm thông tin đầu ra vẫn là nền tảng.

### 7.4. Constant-time comparison chỉ giải quyết một phép so phù hợp

Một phép so sánh bí mật có thể cần implementation thích hợp, nhưng đổi cách so một chuỗi không làm toàn bộ search với DB, index, ACL và network trở thành constant-time.

Không dùng một hàm mang tên an toàn để suy ra bảo đảm cho cả request. Bảo đảm phải tương ứng với phạm vi đã được phân tích và kiểm thử.

## 8. Ngân sách truy vấn và cô lập tài nguyên

### 8.1. Giảm khả năng thu thập mẫu không thay việc sửa oracle

Giới hạn tần suất, mức đồng thời và query budget có thể giảm lạm dụng và số quan sát. Chúng cũng bảo vệ tính sẵn sàng.

Tuy nhiên, một oracle rất mạnh có thể tiết lộ thông tin với ít request. Không tuyên bố rate limit tự loại bỏ timing leakage.

### 8.2. Giới hạn chi phí theo cấu trúc query

Có thể giới hạn độ dài, số clause, range, wildcard/prefix, page size, expansion và metadata được yêu cầu theo hợp đồng.

Ngân sách theo cấu trúc công khai giúp tránh request quá đắt mà không cần phản hồi dựa vào số tài liệu bí mật khớp. Dù vậy, chi phí thực tế vẫn cần quan sát và bảo vệ ở nguồn thực thi.

### 8.3. Actor/tenant và tài nguyên dùng chung

Nhiều người có thể dùng chung IP, và một chủ thể có thể dùng nhiều địa chỉ. Chọn chiều quota phù hợp actor/tenant và loại tác vụ, không dựa vào một tín hiệu mạng duy nhất.

Queue, connection pool, cache và worker dùng chung có thể tạo phụ thuộc giữa các tác vụ. Nếu yêu cầu bảo mật bao gồm cô lập mạnh các phụ thuộc đó, cần đánh giá kiến trúc tài nguyên, không chỉ sửa query text.

### 8.4. Lỗi và overload không được mở rộng scope

Không tắt ACL hoặc chuyển sang tìm toàn cục khi scope service chậm. Khi không xác lập được điều kiện bắt buộc, dừng theo hợp đồng an toàn.

Response lỗi cũng không nên báo rằng request bị chậm vì có hit riêng tư. Dữ liệu chẩn đoán nhạy cảm ở kênh nội bộ có quyền thích hợp.

## 9. Đánh giá thực nghiệm có kiểm soát

### 9.1. Thiết kế hai thế giới thử nghiệm

Chuẩn bị hai trạng thái mà actor có cùng dữ liệu được phép thấy và gửi cùng query:

- Một trạng thái không có dữ kiện bí mật mục tiêu.
- Một trạng thái có dữ kiện đó nhưng actor vẫn không được phép biết.

Đảm bảo index đã phản ánh trạng thái cần thử theo kịch bản. Nếu index chưa cập nhật, hai trạng thái thực thi có thể vẫn giống nhau và tạo kết luận âm tính giả.

Không dùng hai môi trường khác hẳn phần cứng, topology hoặc quyền rồi gán mọi chênh lệch cho dữ kiện bí mật.

### 9.2. Kiểm soát các nguồn nhiễu

Cần xét kết nối/TLS, kích thước request, auth path, tải đồng thời, warm/cold cache, kích thước dữ liệu công khai và trạng thái nguồn phụ thuộc.

Đảo hoặc xen kẽ thứ tự có kiểm soát thay vì chạy hết nhóm A trước rồi nhóm B sau trong lúc tải hệ thống thay đổi. Tách các chế độ cache nếu chúng trả lời những câu hỏi khác nhau.

Không cố làm mọi thứ giống nhau đến mức loại bỏ chính cơ chế cache/index đang muốn đánh giá. Cần ghi rõ giả định và biến kiểm soát, không chỉ áp một công thức đo duy nhất.

### 9.3. Minh họa harness Java trong môi trường kiểm thử

Các helper sau là hợp đồng minh họa. Đoạn mã không thực hiện kiểm tra một hệ thống thật trong bài học này.

```java
List<TimingObservation> observations = new ArrayList<>();

for (TrialCase trial : trialPlan.randomizedCases()) {
    fixtures.prepareComparableWorld(trial);
    fixtures.awaitRequiredIndexState(trial);
    cacheRegime.prepareAccordingToPlan(trial);

    long started = System.nanoTime();
    SearchResponse response = testClient.searchAs(
            restrictedActor, fixedSearchRequest);
    long elapsed = System.nanoTime() - started;

    observations.add(new TimingObservation(
            trial.label(),
            elapsed,
            response.normalizedPublicObservation()));
}
```

Các bước chuẩn bị không nằm trong khoảng đo, nhưng có thể ảnh hưởng cache và tải sau đó. Harness cần thực hiện kế hoạch kiểm soát tương ứng, không chỉ gọi một helper có tên “comparable”.

Đo tại test client phản ánh đường quan sát của harness đó. Một microbenchmark gọi trực tiếp repository không tự đại diện cho khả năng quan sát qua mạng của người dùng.

### 9.4. Phân tích phân phối, không chỉ một lần nhanh/chậm

Xem các phân phối, độ chồng lấp, mức chênh lệch và độ ổn định dưới điều kiện phù hợp. Median hoặc tail latency riêng lẻ không chứng minh được bí mật có thể suy ra đáng tin.

Một khác biệt có ý nghĩa thống kê chưa chắc có tác dụng thực tế trong ngân sách truy vấn của actor. Ngược lại, nhiễu ở một môi trường đo không chứng minh mọi môi trường đều an toàn.

Nếu dùng mô hình phân loại để đánh giá khả năng phân biệt, cần dữ liệu đánh giá tách biệt và kiểm soát yếu tố gây nhầm. Không chỉ báo kết quả trên chính các mẫu đã dùng chọn ngưỡng.

### 9.5. Kết luận đúng mức bằng chứng

Một kết luận hữu ích nêu bí mật, quyền actor, điều kiện đo, cơ chế quan sát, mức phân biệt tìm thấy và giới hạn còn lại.

Không ghi “không có timing leakage” chỉ vì một lần test nằm dưới một ngưỡng tùy ý. Cũng không kết luận có tài liệu bí mật chỉ vì một query thực tế chậm mà chưa loại các nguyên nhân công khai.

## 10. Response, audit và xử lý phát hiện

### 10.1. Giữ hợp đồng không tiết lộ

Response cho đối tượng ngoài quyền cần đúng chính sách về tồn tại, body, metadata và các đường liên quan. Không công khai số candidate bị loại, nhánh ACL hay lý do trễ có liên quan dữ liệu riêng tư.

Các timestamp/metadata về nguồn cũng cần ý nghĩa phù hợp. Không vô tình công bố trạng thái toàn index hoặc thay đổi corpus riêng tư nếu thông tin đó nằm ngoài quyền.

### 10.2. Quan sát nội bộ đủ để tìm nguyên nhân

Có thể theo dõi thời gian theo stage, số candidate đã xét, số lần gọi quyền, cache regime, index/ACL version và query plan reference trong phạm vi cần thiết.

Query text và document reference có thể nhạy cảm. Không mặc định lưu nguyên từ khóa, nội dung hit, credential hoặc response riêng tư. Giới hạn quyền xem và vòng đời dữ liệu chẩn đoán.

### 10.3. Không suy động cơ từ một query đắt

Một người hợp lệ có thể tìm từ hiếm, dùng bộ lọc được hỗ trợ hoặc gặp nguồn chậm. Chênh lệch timing không tự chứng minh họ đang dò bí mật.

Có thể tổng hợp mẫu lặp, nhiều đối tượng, loại query và ngữ cảnh theo policy để phát hiện lạm dụng. Không để một phản ứng tự động tạo thêm thông tin rằng query đã khớp dữ liệu ẩn.

### 10.4. Khắc phục theo cơ chế, không chỉ giảm cảnh báo

Nếu nguyên nhân là post-filter candidate bí mật, sửa kế hoạch/scope và dữ liệu hỗ trợ. Nếu là metadata, loại phần công bố không cần thiết. Nếu là ACL trễ, xử lý độ mới và ranh giới nguồn.

Sau sửa, chạy lại kịch bản chức năng và đánh giá timing có kiểm soát. Không chỉ tăng ngưỡng detector hoặc thêm delay để biểu đồ trông phẳng hơn.

## 11. Kiểm thử và regression

| Kịch bản | Điều cần kiểm tra |
|---|---|
| Cùng query, dữ liệu được phép giữ nguyên, chỉ thêm tài liệu bí mật | Quan sát không được tiết lộ trực tiếp và timing được đánh giá theo threat model |
| ID không tồn tại so với ID riêng tư | Không có nhánh response/chi phí tồn tại không cần thiết mà policy muốn che |
| Nhiều candidate ngoài quyền rồi post-filter | Không có vòng công việc bí mật không kiểm soát; cơ chế khắc phục được đo |
| Không trả count nhưng engine vẫn tính toàn cục | Kiểm tra cả công việc backend, không chỉ JSON |
| Snippet/facet/autocomplete dùng corpus hạn chế | Không công bố hoặc thực hiện phần xử lý không cần thiết ngoài scope |
| Filter theo field không được phép suy ra | Bị chặn theo hợp đồng, không tạo oracle thuộc tính |
| Cache warm/cold và namespace giữa actor/tenant | Không trả sai dữ liệu; kênh timing được đánh giá riêng |
| Thu hồi quyền nhưng index còn cũ | Không lộ hit/metadata và không bỏ qua ảnh hưởng recheck |
| Header timing/cache/debug được bật | Không công khai chẩn đoán vượt policy |
| Scope source lỗi hoặc query vượt ngân sách | Không fallback tìm rộng hoặc tiết lộ có tài liệu ẩn |
| Dữ liệu được phép thật sự thay đổi | Query vẫn đúng chức năng; không đánh đồng mọi thay đổi timing với rò rỉ |
| Actor có quyền tìm tài liệu mục tiêu | Positive case vẫn hoạt động, không chặn tất cả để làm timing giống nhau |

### 11.1. Tách chức năng, rò rỉ nội dung và rò rỉ thời gian

Đầu tiên kiểm tra item, count, facet, gợi ý và field riêng tư không bị lộ. Sau đó đánh giá timing với dữ liệu/actor/query được kiểm soát.

Không dùng việc trả ít dữ liệu hơn hoặc luôn lỗi để làm kết quả timing “đạt” trong khi API không còn đáp ứng chức năng hợp lệ.

### 11.2. Tránh assertion thời gian quá giòn

Một test buộc mỗi request phải bằng nhau tới từng mili giây thường phản ánh scheduler và môi trường hơn là một bảo đảm bảo mật có ý nghĩa.

Giữ regression chức năng cho các cơ chế như không `exists` toàn cục, scope ở đúng pipeline, metadata bị giới hạn và không N+1 ngoài kiểm soát. Đánh giá phân phối timing cần kế hoạch đo phù hợp và kết luận theo bằng chứng.

### 11.3. Lưu khả năng tái hiện

Ghi seed/thứ tự trial, cấu hình cache/index, phạm vi dữ liệu, phiên bản code/policy và các giả định cần thiết. Không đưa dữ liệu bí mật thật vào fixture chỉ để tạo một nhãn đo.

Khi thay engine, schema ACL, query planner, cache hoặc metadata, xem lại các đường có thể làm công việc phụ thuộc tài liệu ngoài quyền dù policy logic không đổi.

## 12. Tự rà soát search timing leakage

Trước khi kết luận một search endpoint giữ được bí mật, hãy trả lời:

1. Dữ kiện ngoài quyền nào có thể bị suy ra và actor quan sát được những gì?
2. Đã giữ nguyên dữ liệu được phép khi so sánh hay đang nhầm chi phí query bình thường với bí mật?
3. Có tìm rộng, kiểm tra ACL từng candidate hoặc nhánh exists trước scope không?
4. Count, snippet, autocomplete hoặc debug có xử lý/công bố dữ liệu ngoài quyền không?
5. Scope logic có thực sự giảm công việc ngoài quyền trong engine, hay chỉ lọc response cuối?
6. Cache/index cũ và nguồn quyền có đáp ứng mức độ mới cần thiết không?
7. Header và metadata có làm việc đo tín hiệu bí mật dễ hơn không?
8. Rate limit/padding đang là lớp bổ sung hay bị dùng thay cho sửa cơ chế rò rỉ?
9. Thực nghiệm có kiểm soát nhiễu, phân phối và khả năng phân biệt ngoài tập đã chọn ngưỡng không?
10. Các luồng hợp lệ vẫn hoạt động và kết luận có nói đúng giới hạn bằng chứng không?

Bảo vệ trước search timing leakage cần giảm sự phụ thuộc có thể quan sát giữa dữ liệu bí mật và quá trình trả lời. Scope đúng là nền tảng, nhưng kế hoạch thực thi, cache, metadata và cách đo cũng phải được xem xét; một body rỗng hoặc một khoảng sleep không tự tạo bảo đảm đó.
