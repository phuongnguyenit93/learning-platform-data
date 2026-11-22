# Phân biệt công sức thực hiện với thời gian chờ theo lịch

Trong module **VALIDATION_TESTING_STRATEGY**, lập kế hoạch nguồn lực kiểm thử đòi hỏi phân biệt rõ **công sức thực hiện** với **thời gian chờ theo lịch**. Hai đại lượng này thường bị gộp thành một con số “thời gian kiểm thử”, khiến kế hoạch thiếu chính xác, khó giải thích vì sao công việc bị trễ và dễ phân bổ sai người hoặc môi trường.

**Công sức thực hiện (effort)** là lượng lao động hoặc năng lực chủ động cần bỏ ra để hoàn thành công việc, thường được đo bằng giờ công hoặc ngày công. **Thời gian chờ theo lịch (calendar waiting time)** là khoảng thời gian công việc chưa thể tiến triển vì phải đợi một mốc, tài nguyên, người phê duyệt, môi trường, kết quả từ hệ thống khác hoặc khung thời gian đã lên lịch. **Thời gian lịch (elapsed/calendar duration)** là khoảng thời gian thực tế từ lúc bắt đầu đến lúc hoàn tất; nó có thể bao gồm công sức, thời gian máy chạy, thời gian chờ và thời gian ngoài giờ làm việc.

Ví dụ, một tester cần 3 giờ để chuẩn bị và thực hiện kiểm thử, nhưng phải đợi môi trường được cấp trong 2 ngày và chờ phê duyệt dữ liệu thêm nửa ngày. Công sức của tester vẫn là 3 giờ, trong khi thời gian hoàn tất theo lịch có thể là nhiều ngày. Nếu chỉ ghi “kiểm thử mất 3 giờ”, kế hoạch không phản ánh ngày bàn giao thực tế. Nếu ghi “kiểm thử mất 3 ngày công”, nhóm lại phóng đại công sức và có thể dự trù nguồn lực sai.

Bài học này trình bày cách phân biệt effort, thời gian thực thi, thời gian chờ và thời gian lịch; cách đo và ước lượng từng đại lượng; cách đưa phụ thuộc, lịch làm việc, năng lực và giới hạn tài nguyên vào kế hoạch; cách theo dõi thời gian chờ trong quy trình kiểm thử; và cách báo cáo để quyết định nguồn lực có căn cứ. Mục tiêu là dự báo được cả lượng công việc cần làm lẫn thời điểm có thể hoàn tất.

## 1. Phân biệt các khái niệm thời gian

### 1.1. Công sức thực hiện (effort)

Effort là lượng công việc chủ động cần người hoặc nhóm thực hiện. Trong kiểm thử phần mềm, effort có thể gồm:

- Phân tích yêu cầu và rủi ro.
- Thiết kế test case, test data và oracle.
- Chuẩn bị môi trường hoặc cấu hình.
- Viết, review và bảo trì script tự động.
- Thực thi kiểm thử thủ công.
- Điều tra lỗi và thu thập bằng chứng.
- Tái kiểm tra bản sửa và chạy hồi quy.
- Phân tích kết quả, báo cáo và xác nhận hoàn tất.

Effort thường được đo bằng:

- **Person-hour (giờ công):** một người làm việc trong một giờ.
- **Person-day (ngày công):** lượng công sức quy ước tương đương một ngày làm việc của một người.
- **Person-week (tuần công):** lượng công sức quy ước tương đương một tuần làm việc của một người.

Đơn vị ngày công hoặc tuần công phải nêu rõ quy ước. Ví dụ, tổ chức có thể quy ước một ngày công bằng 8 giờ làm việc hữu ích, nhưng ngày làm việc thực tế có thể ngắn hơn do họp, hỗ trợ hoặc nhiệm vụ khác. Không nên mặc định mọi tổ chức có cùng định nghĩa.

Effort không phải số ngày trên lịch. Một công việc cần 16 giờ công có thể được thực hiện trong 2 ngày bởi một người có đủ thời gian, trong 1 ngày bởi hai người nếu công việc chia được, hoặc kéo dài một tuần nếu người thực hiện chỉ có thể dành vài giờ mỗi ngày.

### 1.2. Thời gian thực thi (execution time)

Thời gian thực thi là khoảng thời gian một hoạt động đang chạy. Cần phân biệt hai loại:

- **Thời gian thực thi có người tham gia:** khoảng thời gian người kiểm thử trực tiếp thao tác, quan sát hoặc đưa ra quyết định.
- **Thời gian máy thực thi:** thời gian CI, test runner, trình duyệt, simulator hoặc hệ thống kiểm thử đang chạy.

Ví dụ, một suite tự động chạy trong 45 phút. Tester có thể chỉ cần 10 phút để khởi chạy và xem kết quả; phần lớn 45 phút là thời gian máy thực thi. Thời gian máy chạy không nên được tính thành 45 phút effort của tester, dù runner, thiết bị hoặc môi trường vẫn bị chiếm dụng trong khoảng đó.

Thời gian thực thi là một phần của elapsed duration. Nó có thể tiêu thụ tài nguyên máy mà không tiêu thụ tương ứng giờ công của con người.

### 1.3. Thời gian chờ (waiting time)

Waiting time là khoảng thời gian công việc không thể tiến triển vì đang chờ điều kiện hoặc nguồn lực. Trong quy trình kiểm thử, có thể gặp:

- Chờ môi trường hoặc tài khoản được cấp.
- Chờ dữ liệu kiểm thử được tạo hoặc phê duyệt.
- Chờ build hoặc deployment hoàn tất.
- Chờ CI runner hoặc thiết bị kiểm thử rảnh.
- Chờ nhà cung cấp hoặc sandbox phản hồi.
- Chờ developer sửa lỗi.
- Chờ người có thẩm quyền xác nhận quy tắc nghiệp vụ.
- Chờ cửa sổ triển khai hoặc khung giờ được phép kiểm thử.
- Chờ job nền, xử lý hàng đợi hoặc đồng bộ dữ liệu.
- Chờ phê duyệt bảo mật, quyền truy cập hoặc thay đổi cấu hình.

Thời gian chờ không đồng nghĩa với thời gian không có giá trị. Một số hoạt động chờ là điều kiện cần để công việc tiếp tục. Tuy nhiên, cần ghi nhận riêng để nhận ra nút thắt và tránh cộng nhầm thành effort.

### 1.4. Thời gian lịch (elapsed time / calendar duration)

Elapsed time là khoảng thời gian thực tế từ một mốc bắt đầu đến mốc kết thúc. Nếu một yêu cầu kiểm thử bắt đầu lúc 09:00 thứ Hai và hoàn tất lúc 15:00 thứ Tư, elapsed time là 54 giờ đồng hồ, bất kể người kiểm thử chỉ làm 7 giờ.

Elapsed time có thể bao gồm:

- Thời gian làm việc chủ động.
- Thời gian máy thực thi.
- Thời gian xếp hàng.
- Thời gian chờ phụ thuộc.
- Buổi tối, cuối tuần và ngày nghỉ.
- Thời gian tạm dừng hoặc bị chặn.

Khi báo cáo, cần nói rõ đang dùng **giờ đồng hồ**, **ngày lịch** hay **ngày làm việc**. Hai cách tính này khác nhau khi có cuối tuần, ngày lễ hoặc lịch làm việc theo ca.

### 1.5. Lead time và cycle time

Hai khái niệm này thường được dùng khi phân tích dòng công việc:

- **Lead time:** thời gian từ lúc yêu cầu được ghi nhận hoặc cam kết đến khi kết quả được bàn giao.
- **Cycle time:** thời gian từ lúc công việc thực sự bắt đầu được xử lý đến khi hoàn tất.

Một yêu cầu có thể nằm trong backlog 5 ngày trước khi được nhận xử lý, sau đó mất 3 ngày từ lúc bắt đầu đến lúc hoàn tất. Lead time là 8 ngày theo cách xác định mốc trên; cycle time là 3 ngày. Effort bên trong 3 ngày có thể chỉ là 9 giờ công.

Hãy định nghĩa mốc bắt đầu và kết thúc trong quy trình của nhóm. Nếu không, số liệu lead time và cycle time giữa các nhóm sẽ không thể so sánh.

### 1.6. Bảng phân biệt nhanh

| Đại lượng | Câu hỏi trả lời | Đơn vị thường dùng | Ví dụ |
|---|---|---|---|
| Effort | Cần bao nhiêu công sức của con người? | Giờ công, ngày công | Tester làm 4 giờ |
| Human active time | Người trực tiếp thao tác trong bao lâu? | Giờ, phút | Điều tra lỗi trong 50 phút |
| Machine execution time | Máy chạy tác vụ trong bao lâu? | Giây, phút, giờ | CI suite chạy 35 phút |
| Waiting time | Công việc phải đợi bao lâu? | Giờ, ngày lịch | Đợi môi trường 1,5 ngày |
| Elapsed duration | Từ bắt đầu đến kết thúc mất bao lâu? | Giờ/ngày lịch | Hoàn tất sau 3 ngày |
| Lead time | Từ lúc yêu cầu được ghi nhận đến lúc bàn giao mất bao lâu? | Ngày lịch hoặc ngày làm việc | 8 ngày |
| Cycle time | Từ lúc bắt đầu xử lý đến lúc hoàn tất mất bao lâu? | Ngày lịch hoặc ngày làm việc | 3 ngày |

Các đại lượng có thể chồng lấp về thời gian trên trục lịch nhưng không được cộng hoặc quy đổi tùy tiện. Ví dụ, một suite chạy 30 phút trong lúc tester phân tích kết quả của một suite khác không tạo thành 60 phút elapsed time.

## 2. Vì sao phải tách effort khỏi thời gian chờ?

### 2.1. Lập kế hoạch nguồn lực chính xác

Nếu một nhiệm vụ cần 6 giờ công nhưng phải đợi môi trường 2 ngày, việc cấp thêm tester không nhất thiết làm ngày hoàn tất sớm hơn. Nút thắt nằm ở môi trường. Ngược lại, nếu công việc cần 40 giờ effort nhưng chỉ có một người rảnh 2 giờ mỗi ngày, lịch hoàn tất sẽ kéo dài dù không có phụ thuộc bên ngoài.

Tách hai đại lượng giúp trả lời đúng câu hỏi:

- Cần bao nhiêu người và kỹ năng nào?
- Khi nào công việc có thể bắt đầu?
- Tài nguyên nào phải sẵn sàng?
- Có thể chạy song song phần nào?
- Nút thắt nằm ở năng lực thực hiện hay ở thời gian chờ?

### 2.2. Tránh ước lượng sai ngày hoàn tất

Effort không trực tiếp quyết định ngày hoàn tất. Ngày hoàn tất còn phụ thuộc:

- Ngày bắt đầu.
- Lịch làm việc và ngày nghỉ.
- Tỷ lệ thời gian người thực hiện có thể dành cho nhiệm vụ.
- Số người có thể làm song song.
- Phụ thuộc giữa các công việc.
- Tài nguyên dùng chung.
- Thời gian máy chạy và cửa sổ thực thi.
- Rủi ro, làm lại và thời gian chờ.

Ví dụ, 12 giờ công không có nghĩa là hoàn thành trong 1,5 ngày lịch. Nếu tester chỉ có thể dành 3 giờ mỗi ngày cho nhiệm vụ đó, cần ít nhất 4 ngày làm việc để hoàn tất phần effort, chưa tính chờ môi trường hoặc sửa lỗi.

### 2.3. Nhận diện đúng nút thắt

Nếu kiểm thử bị trễ, nguyên nhân có thể khác nhau:

- Effort cao hơn dự kiến vì phạm vi hoặc độ phức tạp.
- Người có kỹ năng phù hợp không sẵn sàng.
- Môi trường không ổn định hoặc phải chờ cấp quyền.
- CI runner hoặc thiết bị bị xếp hàng.
- Lỗi cần developer sửa trước khi retest.
- Nghiệp vụ chưa xác nhận expected result.
- Cửa sổ kiểm thử chỉ mở vào một số khung giờ.

Nếu không phân loại, nhóm dễ phản ứng bằng cách tăng người trong khi nút thắt thực tế là phê duyệt, môi trường hoặc phụ thuộc.

### 2.4. Đánh giá hiệu quả cải tiến

Khi tách effort và waiting time, nhóm có thể đo tác động của cải tiến:

- Tự động tạo dữ liệu làm giảm effort chuẩn bị.
- Tăng runner làm giảm thời gian xếp hàng.
- Môi trường ổn định làm giảm thời gian bị chặn.
- Quy trình phê duyệt nhanh hơn làm giảm waiting time.
- Tự động hóa hồi quy làm giảm effort thực thi lặp lại.
- Cải thiện chất lượng yêu cầu làm giảm effort làm rõ và làm lại.

Nếu chỉ nhìn tổng elapsed time, khó biết cải tiến nào đã tạo ra thay đổi và thay đổi đến từ đâu.

## 3. Phân rã một công việc kiểm thử thành effort và thời gian chờ

### 3.1. Dùng cấu trúc công việc (work breakdown)

Chia công việc thành các hoạt động đủ nhỏ để ước lượng và theo dõi. Ví dụ cho một tính năng thanh toán:

| Hoạt động | Effort dự kiến | Thời gian chờ hoặc máy chạy | Điều kiện phụ thuộc |
|---|---:|---|---|
| Làm rõ quy tắc | 1,5 giờ | Chờ nghiệp vụ xác nhận có thể 1 ngày | Người phụ trách nghiệp vụ |
| Chuẩn bị dữ liệu | 2 giờ | Chờ tài khoản test 4 giờ | Quyền và môi trường |
| Thiết kế test | 3 giờ | Không đáng kể | Quy tắc đã xác nhận |
| Viết automation | 5 giờ | CI chạy 20 phút | API và môi trường sẵn sàng |
| Kiểm thử tích hợp | 2 giờ | Chờ sandbox 30 phút | Nhà cung cấp |
| Điều tra và báo cáo | 2 giờ | Có thể chờ log/trace được xuất | Observability |

Bảng này tách effort chủ động khỏi các khoảng chờ. Cần tránh cộng toàn bộ thời gian chờ của các hoạt động nếu chúng diễn ra đồng thời hoặc chồng lấp.

### 3.2. Ghi nhận thời gian theo trạng thái

Một cách thực tế là phân loại trạng thái công việc:

- **Ready:** đã đủ điều kiện, có thể bắt đầu.
- **In progress:** đang được thực hiện.
- **Running:** máy hoặc hệ thống đang chạy kiểm thử.
- **Waiting:** đang đợi phụ thuộc hoặc tài nguyên.
- **Blocked:** không thể tiếp tục vì có vấn đề cần xử lý.
- **Review:** đang chờ review hoặc phê duyệt.
- **Done:** hoàn tất theo tiêu chí.

Có thể ghi thời điểm bắt đầu và kết thúc mỗi trạng thái. Nhờ đó, nhóm biết công việc dành bao nhiêu thời gian ở từng trạng thái thay vì chỉ ghi ngày bắt đầu và ngày hoàn tất.

### 3.3. Phân biệt waiting với blocked

Hai trạng thái này có thể được định nghĩa khác nhau trong mỗi nhóm, nhưng nên thống nhất:

- **Waiting:** đang chờ một sự kiện hoặc điều kiện đã biết, ví dụ chờ CI hoàn tất hoặc chờ đến khung giờ kiểm thử.
- **Blocked:** không thể tiến triển vì có vấn đề hoặc quyết định chưa được giải quyết, ví dụ môi trường hỏng, thiếu quyền hoặc yêu cầu mâu thuẫn.

Waiting có thể là trạng thái bình thường trong quy trình. Blocked thường cần người chịu trách nhiệm và hành động tháo gỡ. Cả hai đều không phải effort chủ động, nhưng có ý nghĩa quản lý khác nhau.

### 3.4. Tránh tính trùng thời gian

Một người có thể chờ CI trong khi thực hiện nhiệm vụ khác. Khoảng thời gian đó là waiting time của test run nhưng không nhất thiết là thời gian nhàn rỗi của người đó. Một môi trường có thể chạy test tự động trong khi tester review kết quả khác.

Khi đo, hãy phân biệt theo đối tượng:

- **Task elapsed:** thời gian trôi qua của một nhiệm vụ.
- **Person effort:** thời gian lao động của một người.
- **Resource occupancy:** thời gian một tài nguyên như runner, thiết bị hoặc môi trường bị chiếm dụng.
- **Queue time:** thời gian chờ tài nguyên trước khi bắt đầu.
- **Execution duration:** thời gian tác vụ chạy.

Không cộng những khoảng thời gian trùng nhau thành một tổng duy nhất nếu mục tiêu là tính lead time hoặc effort.

## 4. Ước lượng effort và thời gian lịch riêng biệt

### 4.1. Ước lượng effort theo hoạt động

Với mỗi hoạt động, ước lượng lượng công sức cần thiết dựa trên:

- Phạm vi và số lượng trường hợp.
- Độ phức tạp nghiệp vụ.
- Mức độ hiểu biết hiện có.
- Khả năng tái sử dụng test asset.
- Kỹ năng của người thực hiện.
- Mức độ ổn định của sản phẩm và môi trường.
- Công sức chuẩn bị, điều tra và báo cáo.
- Khả năng phải làm lại.

Nên tách effort theo vai trò khi cần, ví dụ effort của tester, developer, DevOps hoặc chuyên gia nghiệp vụ. Một nhiệm vụ 10 giờ tổng effort có thể gồm 4 giờ tester, 3 giờ developer và 3 giờ platform engineer; không có nghĩa một người cần 10 giờ liên tục.

### 4.2. Ước lượng lịch dựa trên năng lực thực tế

Năng lực sẵn sàng (available capacity) là thời gian một người hoặc tài nguyên thực sự có thể dành cho công việc trong một khoảng lịch.

Ví dụ, một tester làm việc 8 giờ mỗi ngày nhưng chỉ có thể dành 50% thời gian cho dự án do họp, hỗ trợ và các nhiệm vụ khác. Năng lực cho dự án là khoảng 4 giờ/ngày. Một công việc cần 12 giờ effort có thể cần khoảng 3 ngày làm việc nếu không có phụ thuộc và người đó duy trì được mức phân bổ này.

Công thức đơn giản:

```
Thời gian làm việc dự kiến (ngày) =
    Effort (giờ công)
    / Năng lực dành cho nhiệm vụ (giờ/ngày)
```

Công thức này chỉ ước lượng thời gian xử lý theo năng lực. Nó chưa tính ngày nghỉ, phụ thuộc, queue, thời gian máy chạy hoặc làm lại.

### 4.3. Tính đến lịch làm việc và ngày nghỉ

Khi chuyển effort thành ngày hoàn tất, cần xác định:

- Giờ làm việc trong ngày.
- Ngày làm việc trong tuần.
- Ngày lễ và ngày nghỉ của nhóm.
- Ca trực hoặc lịch làm việc theo múi giờ.
- Khung giờ môi trường được phép sử dụng.
- Thời gian bảo trì hoặc đóng băng triển khai.
- Người thay thế khi người phụ trách vắng mặt.

Ví dụ, 8 giờ effort bắt đầu lúc 15:00 thứ Sáu có thể không hoàn tất lúc 23:00 cùng ngày nếu nhóm chỉ làm việc đến 17:00. Phần còn lại được thực hiện vào ngày làm việc tiếp theo.

### 4.4. Dùng ước lượng theo khoảng khi có bất định

Không nên tạo độ chính xác giả khi chưa biết phụ thuộc. Có thể ước lượng theo khoảng:

- Optimistic: nếu điều kiện thuận lợi và không phải làm lại.
- Most likely: theo kinh nghiệm và điều kiện thông thường.
- Pessimistic: nếu có phụ thuộc chậm, lỗi hoặc cần điều tra thêm.

Ví dụ, effort thiết kế kiểm thử có thể ước lượng 3–5 giờ, trong khi chờ xác nhận nghiệp vụ có thể từ vài giờ đến 2 ngày lịch. Hai khoảng này cần theo dõi riêng vì cách giảm bất định khác nhau.

### 4.5. Không quy đổi story point trực tiếp thành ngày công

Story point hoặc đơn vị tương đối phản ánh độ phức tạp, bất định và khối lượng tương đối theo cách làm việc của nhóm. Không nên coi 1 point bằng một số giờ cố định nếu nhóm chưa có dữ liệu và quy ước phù hợp.

Nếu dùng velocity để dự báo sprint, hãy kết hợp với lịch nhóm, năng lực, phụ thuộc và lịch sử hoàn tất. Velocity không phải phép đo trực tiếp effort cá nhân và không thể tự chuyển thành ngày lịch cho từng nhiệm vụ.

## 5. Tính đến phụ thuộc và đường găng

### 5.1. Công việc kiểm thử có quan hệ trước–sau

Một số hoạt động chỉ bắt đầu khi điều kiện trước đó hoàn tất:

- Test design cần yêu cầu hoặc quy tắc đã được làm rõ.
- Integration test cần dịch vụ và dữ liệu sẵn sàng.
- E2E cần deployment hoàn tất.
- Retest cần bản sửa được triển khai.
- Regression cần build ổn định.
- Performance test cần hạ tầng và dataset được chuẩn bị.

Một nhiệm vụ có effort nhỏ vẫn có thể quyết định ngày hoàn tất nếu nó nằm trên chuỗi phụ thuộc dài.

### 5.2. Sơ đồ phụ thuộc minh họa

~~~mermaid
flowchart LR
    A[Làm rõ yêu cầu<br/>2h effort] --> B[Thiết kế test<br/>4h effort]
    C[Cấp môi trường<br/>Chờ 1 ngày] --> D[Chuẩn bị dữ liệu<br/>2h effort]
    B --> E[Thực thi integration<br/>3h effort]
    D --> E
    E --> F[Phân tích và báo cáo<br/>2h effort]
~~~

Trong ví dụ, thời gian cấp môi trường là chờ theo lịch. Nếu môi trường chưa sẵn sàng, nhóm có thể thiết kế test song song nhưng không thể hoàn tất integration test. Ngày hoàn tất phụ thuộc vào nhánh có thời gian kết thúc muộn nhất.

### 5.3. Đường găng (critical path)

Đường găng là chuỗi hoạt động phụ thuộc quyết định thời gian hoàn tất sớm nhất của toàn bộ kế hoạch. Trễ ở một hoạt động trên đường găng thường làm trễ mốc hoàn tất, trừ khi có thể thay đổi trình tự hoặc nguồn lực.

Trong kiểm thử, đường găng có thể đi qua:

- Phê duyệt quy tắc.
- Cấp môi trường.
- Triển khai build.
- Thực thi test tích hợp.
- Sửa lỗi chặn.
- Retest và phê duyệt.

Tăng thêm tester không nhất thiết rút ngắn đường găng nếu nút thắt là một môi trường dùng chung hoặc quyết định từ bên ngoài.

### 5.4. Song song hóa có điều kiện

Có thể chạy song song khi:

- Công việc độc lập về dữ liệu và trạng thái.
- Có đủ người với kỹ năng phù hợp.
- Môi trường và runner đủ năng lực.
- Không có xung đột khi ghi dữ liệu.
- Kết quả có thể hợp nhất và đánh giá rõ ràng.

Không phải mọi công việc đều chia đôi được. Hai người cùng viết test cho một luồng có thể tăng effort phối hợp hoặc tạo xung đột. Cần đánh giá chi phí chia nhỏ, giao tiếp và tích hợp.

## 6. Đo thời gian chờ trong quy trình kiểm thử

### 6.1. Phân loại nguồn chờ

Có thể dùng các mã lý do thống nhất:

| Mã | Nguồn chờ | Ví dụ | Hướng cải thiện |
|---|---|---|---|
| ENV | Môi trường | Chờ cấp hoặc sửa môi trường | Tự động hóa provisioning, tăng độ ổn định |
| DATA | Dữ liệu | Chờ seed, tài khoản hoặc phê duyệt dữ liệu | Factory, self-service và quy trình dữ liệu |
| BUILD | Build/deployment | Chờ artifact hoặc rollout | Tối ưu pipeline và cache an toàn |
| QUEUE | Xếp hàng tài nguyên | Chờ runner hoặc thiết bị | Điều phối, tăng capacity hoặc ưu tiên |
| APPROVAL | Phê duyệt | Chờ nghiệp vụ, bảo mật hoặc release owner | Xác định SLA và người thay thế |
| EXT | Phụ thuộc ngoài | Chờ sandbox hoặc nhà cung cấp | Mock có kiểm soát, sandbox ổn định, lịch phối hợp |
| DEFECT | Sửa lỗi | Chờ bản sửa và triển khai lại | Triage, ownership và vòng phản hồi |
| WINDOW | Khung lịch | Chờ cửa sổ triển khai hoặc kiểm thử | Đặt lịch sớm, mở thêm khung phù hợp |
| ASYNC | Xử lý bất đồng bộ | Chờ queue, job hoặc đồng bộ | Theo dõi trạng thái và điều kiện hoàn tất |

Mã lý do nên đủ chi tiết để phân tích nhưng không quá nhiều đến mức người dùng khó chọn. Nhóm có thể bắt đầu với vài loại chính rồi điều chỉnh theo dữ liệu thực tế.

### 6.2. Ghi timestamp cho từng chuyển trạng thái

Với mỗi công việc hoặc test run, ghi các mốc quan trọng:

- Created / requested.
- Ready.
- Started.
- Submitted to queue.
- Execution started.
- Execution completed.
- Waiting for review.
- Unblocked.
- Retest started.
- Done.

Từ các mốc này, có thể tính:

- Thời gian từ yêu cầu đến khi sẵn sàng.
- Thời gian xếp hàng.
- Thời gian thực thi.
- Thời gian chờ review.
- Thời gian bị blocked.
- Thời gian từ lần chạy đầu đến khi xác nhận cuối.

Không cần ghi mọi timestamp nếu không có giá trị quản lý. Chọn mốc gắn với quyết định hoặc nút thắt cần cải thiện.

### 6.3. Đo waiting time theo từng nhóm nguyên nhân

Ví dụ, một test run có thể trải qua:

| Giai đoạn | Khoảng thời gian | Phân loại |
|---|---:|---|
| Chờ môi trường | 1 ngày làm việc | ENV |
| Chuẩn bị và chạy thủ công | 3 giờ | Effort |
| Chờ runner | 40 phút | QUEUE |
| CI thực thi | 25 phút | Machine execution |
| Phân tích kết quả | 45 phút | Effort |
| Chờ xác nhận nghiệp vụ | 4 giờ | APPROVAL |
| Cập nhật báo cáo | 30 phút | Effort |

Effort của con người là 4 giờ 15 phút. Thời gian chờ là 1 ngày làm việc cộng 40 phút và 4 giờ, nếu các khoảng không chồng lấp. Thời gian máy thực thi là 25 phút. Elapsed time được tính từ mốc bắt đầu đến mốc kết thúc trên lịch, có xét giờ làm việc và thời điểm thực tế; không phải tổng đơn giản của mọi dòng nếu có chồng lấp.

### 6.4. Theo dõi tuổi của công việc đang chờ

Một chỉ số hữu ích là tuổi của yêu cầu đang ở trạng thái waiting hoặc blocked. Công việc chờ lâu có thể cần escalations dù effort còn lại rất nhỏ.

Có thể theo dõi:

- Số lượng công việc đang chờ theo lý do.
- Thời gian chờ trung vị và p90.
- Công việc chờ lâu nhất.
- Số công việc vượt SLA nội bộ.
- Tỷ lệ công việc bị blocked hơn một ngưỡng.
- Số lần một nhiệm vụ chuyển qua lại giữa in progress và waiting.

Không chỉ nhìn trung bình; một số ít yêu cầu chờ rất lâu có thể ảnh hưởng nghiêm trọng đến release.

## 7. Quản lý năng lực và tài nguyên dùng chung

### 7.1. Phân biệt năng lực con người với tài nguyên kỹ thuật

Nguồn lực kiểm thử không chỉ là số tester. Có thể gồm:

- Tester, developer, QA lead và chuyên gia nghiệp vụ.
- CI runner, agent, container và máy ảo.
- Thiết bị di động, trình duyệt và license.
- Môi trường integration, staging hoặc sandbox.
- Tài khoản, tenant và dữ liệu thử.
- Thiết bị phần cứng, lab hoặc mạng chuyên dụng.
- Dịch vụ đối tác và quota API.

Một test có thể cần 1 giờ effort của tester nhưng phải giữ thiết bị lab trong 4 giờ. Cần ghi riêng effort người và thời gian chiếm dụng tài nguyên.

### 7.2. Tính năng lực sẵn sàng

Năng lực thực tế cần trừ thời gian dành cho hoạt động khác:

- Họp và trao đổi.
- Hỗ trợ production.
- Review và mentoring.
- Nghỉ phép, ngày lễ.
- Công việc vận hành hoặc trực.
- Nhiệm vụ ưu tiên khác.

Ví dụ, nhóm có 3 tester, mỗi người làm 8 giờ/ngày. Nếu trung bình mỗi người dành 60% thời gian cho kế hoạch kiểm thử, năng lực dự kiến là:

```
3 người × 8 giờ/ngày × 60% = 14,4 giờ công/ngày
```

Đây là năng lực ước lượng, không phải cam kết rằng mọi giờ đều có thể dùng cho cùng một loại công việc. Cần xem xét kỹ năng, lịch và phân bổ thực tế.

### 7.3. Tài nguyên dùng chung tạo queue

Nếu nhiều nhóm cùng dùng một môi trường hoặc runner, công việc có thể phải xếp hàng. Tăng số tester không làm giảm queue nếu số runner hoặc thiết bị không tăng.

Cần xác định:

- Tài nguyên nào có giới hạn.
- Ai được quyền đặt lịch hoặc ưu tiên.
- Có thể chạy song song an toàn không.
- Thời gian sử dụng trung bình.
- Tỷ lệ hỏng hoặc thời gian bảo trì.
- Có phương án thay thế không.
- Cách xử lý khi tài nguyên bị chiếm dụng quá lịch.

### 7.4. Tránh sử dụng tài nguyên ở mức tối đa liên tục

Nếu mọi tester, runner hoặc môi trường luôn được phân bổ 100%, một công việc khẩn cấp hoặc sự cố nhỏ có thể tạo queue lớn. Duy trì một phần năng lực dự phòng giúp hấp thụ biến động và xử lý việc bất ngờ.

Không nên đánh giá hiệu quả chỉ bằng tỷ lệ utilization. Utilization cao có thể đi kèm lead time tăng và waiting time dài. Cần cân bằng mức sử dụng, thông lượng, chất lượng và thời gian hoàn tất.

## 8. Lập kế hoạch kiểm thử theo lịch

### 8.1. Lập lịch dựa trên cả effort và phụ thuộc

Một kế hoạch cần thể hiện:

- Effort theo hoạt động và vai trò.
- Người hoặc tài nguyên chịu trách nhiệm.
- Ngày sớm nhất có thể bắt đầu.
- Phụ thuộc và điều kiện sẵn sàng.
- Thời gian máy chạy.
- Khoảng chờ dự kiến.
- Ngày hoàn tất dự kiến.
- Buffer cho bất định.
- Mốc cần quyết định hoặc phê duyệt.

Đừng chỉ cộng effort rồi chia cho số người. Phải xem các hoạt động có thể chạy song song hay không và tài nguyên có đủ để hỗ trợ không.

### 8.2. Ví dụ lập kế hoạch một vòng regression

Giả sử vòng regression có:

- Chuẩn bị dữ liệu: 3 giờ công.
- Review phạm vi: 2 giờ công.
- Chạy suite tự động: 1 giờ máy.
- Kiểm thử thủ công: 6 giờ công.
- Phân tích và báo cáo: 2 giờ công.
- Chờ môi trường: dự kiến 1 ngày làm việc.
- Chờ sửa lỗi chặn: chưa chắc chắn, có thể phát sinh.

Tổng effort người là 13 giờ công. Thời gian máy chạy là 1 giờ. Thời gian chờ môi trường là 1 ngày làm việc. Nếu hai tester có thể làm review và chuẩn bị dữ liệu song song trong khi chờ môi trường, một phần công việc không nằm trên đường găng. Ngày hoàn tất cần tính theo lịch và phụ thuộc thực tế, không phải lấy 13 giờ chia cho 8 rồi cộng 1 ngày một cách máy móc.

### 8.3. Xác định buffer

Buffer là khoảng dự phòng cho bất định, chẳng hạn:

- Môi trường có thể không sẵn sàng đúng hẹn.
- Có thể phát hiện lỗi cần retest.
- Nhà cung cấp có thể phản hồi chậm.
- Dữ liệu cần làm sạch hoặc tạo lại.
- Một người có kỹ năng chuyên biệt có thể vắng mặt.

Nên ghi rõ buffer được dành cho rủi ro nào và điều kiện sử dụng. Không cộng buffer ẩn vào mọi nhiệm vụ rồi làm mất khả năng phân tích sai lệch.

### 8.4. Cập nhật dự báo theo dữ liệu thực tế

Khi có dữ liệu từ các vòng kiểm thử:

- So sánh effort dự kiến và effort thực tế.
- So sánh waiting time dự kiến và thực tế.
- Phân loại nguyên nhân sai lệch.
- Xác định phụ thuộc lặp lại.
- Cập nhật ước lượng và giả định.
- Thông báo sớm khi mốc lịch có nguy cơ trễ.

Không dùng sai lệch để quy trách nhiệm cá nhân. Mục tiêu là cải thiện dự báo và quy trình.

## 9. Đo lường và báo cáo

### 9.1. Chỉ số nên theo dõi

| Chỉ số | Cách hiểu | Câu hỏi quản lý |
|---|---|---|
| Estimated effort | Effort dự kiến | Đã dự trù đúng khối lượng công việc chưa? |
| Actual effort | Effort thực tế | Công việc cần bao nhiêu lao động? |
| Waiting time | Thời gian chờ | Nút thắt nằm ở đâu? |
| Execution duration | Thời gian máy hoặc hoạt động chạy | Test suite hoặc tác vụ mất bao lâu? |
| Cycle time | Từ lúc bắt đầu xử lý đến khi hoàn tất | Dòng công việc nhanh đến đâu? |
| Lead time | Từ lúc yêu cầu được ghi nhận đến khi bàn giao | Người yêu cầu phải chờ bao lâu? |
| Queue time | Thời gian chờ tài nguyên | Có thiếu runner, thiết bị hoặc môi trường không? |
| Rework effort | Effort làm lại | Phần nào tạo ra công việc lặp lại? |
| Blocked age | Tuổi công việc bị chặn | Vấn đề nào cần tháo gỡ ngay? |
| Resource utilization | Mức sử dụng tài nguyên | Năng lực đang được dùng thế nào? |

Không nên dùng một chỉ số riêng lẻ để đánh giá năng suất cá nhân. Ví dụ, actual effort thấp có thể do nhiệm vụ bị chờ nhiều chứ không phải hoàn thành hiệu quả.

### 9.2. Báo cáo theo cả công sức và lịch

Một báo cáo ngắn nên nêu:

- Tổng effort dự kiến và thực tế.
- Effort theo vai trò hoặc nhóm hoạt động.
- Thời gian máy thực thi.
- Waiting time theo nguyên nhân.
- Elapsed duration, lead time hoặc cycle time theo mốc đã định.
- Các công việc đang chờ và tuổi chờ.
- Sai lệch, rủi ro và hành động.
- Dự báo ngày hoàn tất mới.

Ví dụ:

> Vòng kiểm thử có 18 giờ công thực tế so với 16 giờ dự kiến. Suite tự động chạy 55 phút. Elapsed time từ lúc nhận yêu cầu đến bàn giao là 4 ngày làm việc; trong đó 1,5 ngày chờ môi trường và 0,5 ngày chờ xác nhận nghiệp vụ. Phần effort tăng 2 giờ do bổ sung trường hợp lỗi. Nút thắt lịch hiện tại là thời gian cấp môi trường, không phải năng lực tester.

Cách báo cáo này giúp quyết định đúng nơi cần cải thiện.

### 9.3. Phân tích xu hướng thay vì một lần chạy

Một lần đo có thể bị ảnh hưởng bởi tình huống bất thường. Theo dõi nhiều vòng để nhận ra:

- Nhóm nguyên nhân chờ phổ biến.
- Môi trường thường trễ bao lâu.
- Effort retest tăng ở loại lỗi nào.
- Queue runner theo ngày hoặc khung giờ.
- Thay đổi lead time sau khi tự động hóa.
- Tỷ lệ công việc blocked.
- Mức chênh giữa dự kiến và thực tế.

Cần giữ định nghĩa và cách tính nhất quán qua các kỳ để tránh so sánh sai.

## 10. Ví dụ tổng hợp: một lỗi chặn trong kiểm thử tích hợp

Giả sử nhóm cần xác nhận luồng thanh toán sau khi có bản sửa lỗi.

### 10.1. Phân rã công việc

| Công việc | Effort người | Chờ / thời gian máy | Phụ thuộc |
|---|---:|---|---|
| Review lỗi và tiêu chí | 1 giờ | Chờ PO xác nhận 3 giờ | Business owner |
| Chuẩn bị dữ liệu | 1,5 giờ | Chờ tài khoản sandbox 2 giờ | Test data owner |
| Triển khai bản sửa | 2 giờ developer | CI/build chạy 20 phút | Source review |
| Deploy integration | 0,5 giờ | Chờ môi trường 1 giờ | Platform |
| Retest và kiểm tra liên quan | 2 giờ tester | Test runner chạy 15 phút | Deployment |
| Phân tích và đóng lỗi | 1 giờ | Chờ review 2 giờ | QA owner |

Effort người tổng cộng là 8 giờ, gồm các vai trò khác nhau. Thời gian máy chạy là 35 phút. Các khoảng chờ có thể nối tiếp hoặc chồng lấp tùy lịch; cần dùng timestamp thực tế để tính elapsed duration.

### 10.2. Cách lập lịch

Trong khi chờ PO xác nhận, tester có thể chuẩn bị phần dữ liệu không phụ thuộc vào quy tắc chưa rõ. Trong khi developer triển khai bản sửa, QA có thể review test case. Khi môi trường sẵn sàng, deployment và retest mới bắt đầu.

Nếu tài khoản sandbox là điều kiện chặn và chỉ có một người cấp, thêm tester không rút ngắn thời gian chờ. Nếu retest cần hai giờ effort nhưng tester chỉ rảnh một giờ mỗi ngày, lịch hoàn tất cần phản ánh năng lực thực tế đó.

### 10.3. Cách báo cáo

- Effort theo vai trò và hoạt động.
- Thời gian máy chạy.
- Thời gian chờ theo PO, sandbox và môi trường.
- Thời gian từ khi lỗi được nhận đến khi đóng.
- Nguyên nhân gây sai lệch so với kế hoạch.
- Hành động để giảm chờ ở vòng tiếp theo.

Nhóm có thể kết luận rằng phần effort phù hợp ước lượng nhưng lead time bị kéo dài do tài khoản sandbox và phê duyệt. Đây là thông tin hữu ích để cải thiện quy trình cấp quyền và chuẩn bị test data.

## 11. Những sai lầm thường gặp

1. **Gộp effort và elapsed time:** làm sai dự toán nhân lực hoặc ngày bàn giao.
2. **Tính thời gian CI thành effort của tester:** không phân biệt máy chạy và lao động con người.
3. **Bỏ qua thời gian chờ:** không nhìn thấy nút thắt do môi trường, dữ liệu hoặc phê duyệt.
4. **Cộng tất cả thời gian chờ:** tính trùng những khoảng chờ diễn ra song song.
5. **Giả định một ngày công luôn bằng 8 giờ hữu ích:** bỏ qua họp, hỗ trợ và lịch thực tế.
6. **Chia effort cho số người một cách máy móc:** giả định công việc có thể chia đều và chạy song song hoàn toàn.
7. **Không ghi nguyên nhân waiting/blocked:** chỉ biết công việc trễ mà không biết vì sao.
8. **Đánh đồng waiting với blocked:** bỏ qua khác biệt giữa chờ theo quy trình và vấn đề cần tháo gỡ.
9. **Không tính tài nguyên dùng chung:** tăng người nhưng runner, thiết bị hoặc môi trường vẫn là nút thắt.
10. **Tối đa hóa utilization:** tạo queue và làm giảm khả năng xử lý việc bất ngờ.
11. **Dùng story point như giờ công cố định:** tạo độ chính xác giả và so sánh sai.
12. **Không cập nhật dự báo:** giữ ngày hoàn tất cũ dù phụ thuộc hoặc năng lực đã thay đổi.
13. **Dùng một chỉ số để đánh giá cá nhân:** bỏ qua độ phức tạp và thời gian chờ ngoài kiểm soát.
14. **Không định nghĩa mốc lead time/cycle time:** số liệu giữa nhóm không thể so sánh.

## 12. Checklist phân biệt công sức thực hiện với thời gian chờ theo lịch

- [ ] Effort được ước lượng riêng theo hoạt động và vai trò.
- [ ] Đơn vị person-hour/person-day có quy ước rõ.
- [ ] Thời gian máy thực thi được tách khỏi effort con người.
- [ ] Waiting time được phân loại theo nguồn và nguyên nhân.
- [ ] Waiting và blocked có định nghĩa nhất quán.
- [ ] Mốc bắt đầu/kết thúc của elapsed time, lead time và cycle time được xác định.
- [ ] Các khoảng thời gian chồng lấp không bị cộng trùng.
- [ ] Lịch làm việc, ngày nghỉ, ca và múi giờ được tính đến.
- [ ] Năng lực sẵn sàng phản ánh công việc khác và kỹ năng cần thiết.
- [ ] Phụ thuộc và đường găng được thể hiện trong kế hoạch.
- [ ] Tài nguyên dùng chung như runner, môi trường, thiết bị và sandbox được quản lý.
- [ ] Buffer được gắn với rủi ro và giả định cụ thể.
- [ ] Timestamp chuyển trạng thái được ghi đủ để phân tích waiting time.
- [ ] Effort và thời gian chờ thực tế được so sánh với dự kiến.
- [ ] Báo cáo nêu rõ nguyên nhân trễ và hành động tháo gỡ.
- [ ] Chỉ số được dùng để cải thiện quy trình, không quy kết cá nhân thiếu căn cứ.

Phân biệt công sức thực hiện với thời gian chờ theo lịch giúp kế hoạch kiểm thử phản ánh cả khối lượng lao động lẫn những điều kiện quyết định ngày hoàn tất. Khi effort, thời gian máy chạy, waiting time và elapsed duration được ghi riêng, nhóm có thể phân bổ nguồn lực đúng hơn, nhận diện nút thắt, dự báo mốc bàn giao thực tế và lựa chọn cải tiến có tác động rõ ràng.
