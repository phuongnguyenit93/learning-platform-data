# Tenant isolation test

## 1. Mục tiêu của kiểm thử cô lập tenant

**Tenant isolation test** kiểm tra rằng danh tính, quyền, dữ liệu và trạng thái xử lý của một tenant không được dùng ngoài phạm vi được cấp cho tenant đó.

Trong hệ thống nhiều tenant, cùng một endpoint và cùng một hạ tầng có thể phục vụ nhiều tổ chức. Một người dùng của tenant A có thể đăng nhập hợp lệ nhưng vẫn không được đọc tài nguyên của tenant B. Vì vậy, chỉ kiểm tra request không có token bị từ chối chưa chứng minh cô lập tenant.

Một bộ test cần kiểm tra hai chiều:

- Chủ thể được phép có thể thực hiện đúng chức năng trong phạm vi của mình.
- Chủ thể không có quyền không đọc được dữ liệu, không tạo tác động ghi và không nhận được kết quả phụ ngoài phạm vi.

Điểm thứ hai bao gồm cả đường gián tiếp như tìm kiếm, tổng số bản ghi, cache, tệp export, job nền và công cụ quản trị. Một API đọc chi tiết được bảo vệ đúng chưa đủ để kết luận toàn hệ thống đã cô lập.

## 2. Xác định điều gì được xem là tenant

Trước khi viết test, cần làm rõ tenant được nhận biết và thực thi bằng cơ chế nào. Các hệ thống có thể dùng chung database với trường tenant, tách schema, tách database hoặc kết hợp nhiều cách.

Tenant cũng có thể được chọn qua hostname, đường dẫn hoặc ngữ cảnh tài khoản. Giá trị người gọi lựa chọn không tự chứng minh họ được tham gia tenant đó.

| Thành phần | Câu hỏi cần có câu trả lời |
| --- | --- |
| Danh tính chủ thể | Định danh được quản lý trong namespace nào, có issuer hoặc miền danh tính liên quan không? |
| Membership | Người dùng hoặc workload được cấp quyền vào tenant nào? |
| Tenant được chọn | Giá trị đến từ đâu và được đối chiếu với quyền như thế nào? |
| Tài nguyên | Tenant thực của tài nguyên được xác định từ dữ liệu nào? |
| Quyền quản trị | Quản trị tenant có khác quản trị nền tảng không? |
| Chia sẻ hợp lệ | Có tài nguyên công khai, chia sẻ chéo tenant hoặc quyền ủy nhiệm được cấp rõ không? |

Không mặc định mọi truy cập chéo tenant đều sai nếu sản phẩm có chức năng chia sẻ được phê duyệt. Test cần phân biệt truy cập có grant cụ thể với truy cập chỉ dựa vào việc biết ID hoặc tự đổi tham số.

Tương tự, một người dùng có membership ở cả A và B cần được kiểm tra như một trường hợp riêng. Mục tiêu là giữ đúng phạm vi đang thực hiện và quyền cụ thể, không phải từ chối mọi tài khoản có nhiều membership.

## 3. Dựng fixture đủ để phát hiện nhầm phạm vi

Nên dùng dữ liệu tổng hợp, được tạo trong môi trường kiểm thử có phạm vi rõ. Một bộ fixture tối thiểu có thể gồm:

| Fixture | Tenant | Quyền hoặc đặc điểm |
| --- | --- | --- |
| `viewer_A` | A | Được đọc một tập tài nguyên của A |
| `admin_A` | A | Quản trị tenant A, không có quyền nền tảng |
| `viewer_B` | B | Được đọc một tập tài nguyên của B |
| `member_AB` | A và B | Có membership ở cả hai, quyền có thể khác nhau |
| `worker_A` | A | Workload chỉ phục vụ nhiệm vụ trong A |
| `resource_A` | A | Có marker dữ liệu tổng hợp riêng của A |
| `resource_B` | B | Có marker khác để phát hiện dữ liệu B bị trả nhầm |

Tài khoản quản trị nền tảng nếu có phải là fixture tách biệt. Không dùng nó làm danh tính mặc định của mọi test, vì quyền rộng có thể che mất lỗi kiểm tra phạm vi.

Hai tenant nên có một số dữ liệu giống nhau về tên hoặc khóa cục bộ nếu schema cho phép. Ví dụ, cùng có tài nguyên mang mã nghiệp vụ `CASE-100`. Điều này giúp phát hiện cache hoặc truy vấn chỉ dựa vào mã cục bộ mà quên tenant.

Không cần tạo ID trùng nếu hệ thống yêu cầu ID toàn cục duy nhất. Khi đó vẫn có thể dùng tên hiển thị hoặc khóa nghiệp vụ giống nhau để kiểm tra các nơi tra cứu theo những trường đó.

Các client hoặc phiên test cần độc lập khi mục tiêu là mô phỏng các chủ thể khác nhau. Không để cookie của admin từ bước chuẩn bị vô tình đi theo request của `viewer_A`.

## 4. Lập ma trận quyền trước khi gửi request

Kết quả mong đợi phải dựa trên chính sách độc lập, không lấy từ chính response đang kiểm thử. Ví dụ minh họa không có chia sẻ chéo tenant:

| Chủ thể | Hành động | Tài nguyên | Kết quả mong đợi |
| --- | --- | --- | --- |
| `viewer_A` | Đọc | Tài nguyên A trong phạm vi được cấp | Cho phép |
| `viewer_A` | Đọc | Tài nguyên B | Từ chối |
| `viewer_A` | Ghi | Tài nguyên B | Từ chối và không đổi dữ liệu |
| `admin_A` | Quản trị | Cấu hình tenant A | Theo quyền quản trị A |
| `admin_A` | Quản trị | Cấu hình tenant B | Từ chối |
| `worker_A` | Xử lý job | Tài nguyên B | Từ chối nếu không có quyền riêng |
| Không xác thực | Đọc | Tài nguyên riêng tư | Từ chối theo hợp đồng API |

Trong cùng tenant, vẫn cần những test quyền chi tiết. Hai người cùng thuộc A không nhất thiết được đọc cùng một tài nguyên hoặc cùng xem các trường nhạy cảm.

Một test chéo tenant tốt nên có kiểm tra đối chứng: cùng endpoint đó phải hoạt động với chủ thể B có quyền hợp lệ. Nếu request của A thất bại vì endpoint lỗi hoặc fixture B không tồn tại, đó không phải bằng chứng có giá trị về phân quyền.

## 5. Thay đổi từng đầu vào lựa chọn tenant và tài nguyên

Giữ nguyên danh tính đã xác thực, rồi thay một đầu vào trong mỗi lượt để biết điều kiện nào đang bị kiểm tra.

Các biến thể có thể gồm:

- Đổi tenant trong đường dẫn nhưng giữ token hoặc phiên của A.
- Giữ tenant A nhưng thay ID tài nguyên bằng một ID thật thuộc B.
- Thay tenant hoặc owner trong body của thao tác tạo và cập nhật.
- Đổi query parameter hoặc header dùng chọn phạm vi.
- Thử một hostname tenant khác trong hạ tầng test được cấu hình cho tình huống đó.
- Thay cả parent ID và child ID trong các tài nguyên lồng nhau.

Ví dụ, request có dạng giả định:

```text
GET /tenants/A/cases/{resource_B_id}
```

không được đọc B chỉ vì endpoint đã nhận đường dẫn A. Ngược lại:

```text
GET /tenants/B/cases/{resource_B_id}
```

cũng không được phép với `viewer_A` nếu không có membership hoặc grant phù hợp.

Các đường dẫn này chỉ minh họa ý tưởng, không khẳng định repository có những API tương ứng.

### Tài nguyên lồng nhau và tham chiếu ngoài

Với một đường dẫn như phiếu và tệp đính kèm, kiểm tra tệp thực sự thuộc đúng phiếu và tenant. Chỉ kiểm tra quyền trên parent do người gọi đưa vào rồi tải child toàn cục có thể bỏ qua ràng buộc này.

Khi tạo một bản ghi tham chiếu tới user, nhóm hoặc tài nguyên khác, kiểm tra các tham chiếu cũng nằm trong phạm vi được phép. Bản ghi mới có tenant A nhưng liên kết tới đối tượng B vẫn có thể tạo tác động hoặc rò rỉ về sau.

## 6. Xác nhận từ chối bằng cả dữ liệu và tác động phụ

Một response không thành công chưa đủ nếu backend đã thay đổi dữ liệu trước khi trả lỗi.

Đối với thao tác ghi, cần lưu trạng thái ban đầu, thực hiện request không được phép rồi đối chiếu:

| Loại tác động | Điều cần xác nhận |
| --- | --- |
| Bản ghi chính | Không đổi tenant, owner, nội dung hoặc phiên bản ngoài ý muốn |
| Bản ghi phụ | Không tạo attachment, membership, grant hoặc liên kết trái phép |
| Message hoặc job | Không phát sinh công việc có thể tiếp tục thao tác trái phép |
| Tệp và export | Không tạo hoặc phát hành kết quả ngoài phạm vi |
| Thông báo | Không gửi dữ liệu B tới người nhận hoặc kênh của A |
| Audit | Ghi đúng hành động bị từ chối theo hợp đồng, không ghi thành công giả |

Việc quan sát trạng thái cần dùng cơ chế test đã được cấp quyền và tách biệt khỏi danh tính người gọi. Không mở một API đọc toàn bộ database cho client chỉ để tiện kiểm tra.

Một mã giả minh họa:

```text
before = fixtureStateOf(resource_B)

response = callUpdate(
    authenticatedAs = viewer_A,
    target = resource_B,
    proposedChange = syntheticChange
)

assertDeniedAccordingToApiContract(response)
assertNoProtectedDataDisclosed(response)
assertFixtureStateEquals(resource_B, before)
assertNoUnauthorizedDownstreamWorkWasCreated()
```

Đây là mô tả thiết kế test, không phải API test có sẵn. Mã phản hồi cụ thể có thể được chọn để hạn chế lộ sự tồn tại của tài nguyên; test cần đối chiếu đúng hợp đồng, không áp một mã duy nhất cho mọi ứng dụng.

Với đọc dữ liệu, kiểm tra cả body, header, thông báo lỗi và metadata có thể chứa tên, ID hoặc đường dẫn của B. Tìm marker B là một phép kiểm tra hữu ích, nhưng không thay thế việc xác nhận toàn bộ schema và phạm vi dữ liệu được phép trả.

## 7. Danh sách, tìm kiếm, thống kê và batch

Endpoint chi tiết thường được chú ý hơn những đường tổng hợp. Một bộ test cần bao phủ ít nhất các nhóm sau:

| Đường truy cập | Nội dung cần đối chiếu |
| --- | --- |
| Danh sách phân trang | Mọi phần tử thuộc phạm vi được cấp; tổng số và phân trang nhất quán |
| Tìm kiếm | Kết quả, đoạn trích, gợi ý và metadata không lộ B |
| Thống kê | Số đếm và phép tổng hợp dùng đúng tập dữ liệu |
| Batch đọc | Không đưa dữ liệu B vào response của A |
| Batch ghi | Hành vi toàn bộ hoặc từng phần theo hợp đồng, không sửa phần tử trái phép |
| Export | Tập dữ liệu, tệp kết quả và quyền nhận tệp đều đúng phạm vi |

Nếu dùng kết quả kỳ vọng, nên so sánh tập ID hợp lệ với tập trả về thay vì chỉ kiểm tra số lượng. Một response có đúng 10 phần tử vẫn có thể chứa 9 tài nguyên A và 1 tài nguyên B.

Kiểm tra nhiều trang, bộ lọc rỗng, sắp xếp và truy vấn không có kết quả. Khi quyền được áp dụng sau một phép tổng hợp hoặc sau phân trang, tổng số có thể vô tình phản ánh dữ liệu rộng hơn dù các dòng hiển thị đã được lọc.

Đối với batch, hợp đồng có thể là từ chối toàn bộ hoặc xử lý phần được phép và trả kết quả riêng từng phần tử. Test phải xác nhận đúng lựa chọn đã thiết kế và không để phần không được phép có tác động phụ.

## 8. Cache, connection pool và ngữ cảnh dùng lại

Lỗi cô lập có thể xuất hiện khi request sau sử dụng trạng thái còn lại của request trước. Vì vậy, cần chạy cả cache lạnh và cache đã có dữ liệu.

Một trình tự hữu ích:

```text
1. Chủ thể B đọc tài nguyên B và làm nóng cache.
2. Chủ thể A yêu cầu tài nguyên có khóa dễ bị nhầm.
3. Xác nhận A không nhận dữ liệu đã cache của B.
4. Đảo thứ tự A/B và lặp lại theo phạm vi test.
```

Khóa cache chỉ chứa resource ID hoặc mã nghiệp vụ có thể thiếu tenant; khóa chỉ chứa tenant cũng có thể thiếu quyền chi tiết trong cùng tenant. Test cần phản ánh những yếu tố thực sự quyết định nội dung.

Nếu tầng database sử dụng context tenant gắn với connection, cần kiểm tra cơ chế đặt, khôi phục và dọn context khi connection được trả vào pool. Nếu ứng dụng dùng context gắn với thread, cần kiểm tra tái sử dụng thread và các bước bất đồng bộ.

Các cơ chế row filtering hoặc phân quyền ở database phải được kiểm tra qua đúng danh tính và đường kết nối ứng dụng sử dụng. Test bằng tài khoản database có quyền bỏ qua giới hạn có thể không đại diện cho hành vi của workload thực tế.

Nên thêm tình huống request lỗi giữa chừng, hủy và timeout. Đường cleanup có lỗi có thể để lại context B cho request A tiếp theo dù đường thành công hoạt động đúng.

## 9. Worker, queue và export bất đồng bộ

Một job thường tồn tại lâu hơn request tạo nó. Cần kiểm tra tenant, chủ thể và phạm vi quyền được truyền và tái xác minh theo hợp đồng xử lý.

Các trường hợp đáng chú ý gồm:

- Job A có body khai tài nguyên B nhưng được gửi từ một client không có quyền tương ứng.
- Consumer vừa xử lý job B rồi xử lý job A trên cùng worker.
- Retry hoặc xử lý lại message vẫn giữ đúng tenant.
- Người tạo bị gỡ membership trong thời gian job chờ.
- Job tạo tệp kết quả được lưu tại đúng namespace và chỉ bên được phép nhận.

Metadata trong message không tự là nguồn đáng tin. Consumer cần biết bên gửi nào được phép khai phạm vi đó và hành động được thực hiện dưới quyền nào. Test nên kiểm tra đường xác minh này bằng những fixture và producer kiểm thử được cấp quyền.

Với export, kiểm tra cả lúc tạo job, lúc thực thi và lúc tải kết quả theo chính sách. Một job chỉ lấy dữ liệu A vẫn có thể rò rỉ nếu URL hoặc endpoint nhận tệp cho phép B tải nó ngoài quyền được cấp.

Thông tin cấp quyền trong link tải không nên xuất hiện nguyên vẹn trong báo cáo hoặc log kiểm thử. Nếu tính năng chủ đích hỗ trợ chia sẻ bằng link giới hạn, test cần kiểm tra đúng điều kiện của link đó thay vì mặc định mọi người nhận phải có cùng phiên ứng dụng.

## 10. Membership, quyền quản trị và thay đổi vòng đời

Kiểm thử sau thay đổi quyền giúp phát hiện cache hoặc token cũ giữ phạm vi lâu hơn yêu cầu.

| Thay đổi | Kết quả cần xác định và kiểm tra |
| --- | --- |
| Gỡ membership A | Quyền truy cập A mất hiệu lực theo thời hạn đã cam kết |
| Giữ membership B của cùng người dùng | Không vô tình áp thay đổi A sang B |
| Gỡ vai trò quản trị tenant A | Không còn quản trị A dù phiên đăng nhập vẫn có thể còn |
| Thu hồi quyền workload A | Job và request mới xử lý theo phạm vi thu hồi |
| Chuyển hoặc chia sẻ tài nguyên | Các quyền và cache liên quan thay đổi đúng chính sách |

Nếu hệ thống cho phép độ trễ đồng bộ hoặc thu hồi, cần có thời hạn hội tụ rõ và cách xác nhận trạng thái. Không thêm một khoảng chờ dài tùy ý chỉ để làm test hết thất bại.

Quản trị tenant A không được tự trở thành quản trị nền tảng. Nên kiểm tra các thao tác cấu hình client, mời thành viên, cấp vai trò và liên kết danh tính, vì chúng có thể tạo quyền mới dù không trực tiếp đọc tài nguyên nghiệp vụ.

Việc hai tài khoản có email giống nhau ở những miền danh tính hoặc tenant khác nhau không tự chứng minh chúng là cùng chủ thể. Khi có liên kết tài khoản, kiểm tra cơ chế xác minh và ràng buộc riêng của tính năng; không để phép ghép dữ liệu theo email mở ra quyền chéo tenant.

## 11. Test song song và các bất biến có thể tổng quát hóa

Các kịch bản tuần tự giúp giải thích nguyên nhân. Kịch bản song song giúp phát hiện context dùng chung, race và cache bị ghi đè.

Có thể gửi những giao dịch A và B có dữ liệu đánh dấu riêng qua cùng tập instance hoặc worker, trong phạm vi tải kiểm thử đã xác định. Sau đó kiểm tra mỗi response và tác động tương ứng, thay vì chỉ nhìn tổng số request thành công.

Một bất biến có thể dùng để sinh nhiều trường hợp:

```text
Với mọi subject S và resource R trong tập test:
    nếu không có membership hoặc grant cho phép hành động,
    S không được nhận dữ liệu bảo vệ của R
    và hành động không được tạo tác động ngoài phạm vi.
```

Trường hợp được cấp quyền chia sẻ, quản trị nền tảng hoặc workload phục vụ nhiều tenant cần được đưa vào mô hình kỳ vọng riêng. Không làm bất biến đơn giản đến mức đánh dấu những quyền được cấp có chủ đích là lỗi.

Các test ngẫu nhiên nên lưu seed và fixture để tái hiện. Không dựa vào ID tài nguyên sản xuất hoặc quét một hệ thống ngoài phạm vi để tìm trường hợp chéo tenant.

## 12. Bằng chứng, mức bao phủ và lỗi kết luận

Một báo cáo test nên có chủ thể theo fixture, tenant được chọn, tài nguyên, hành động, phiên bản chính sách, kết quả mong đợi, kết quả thực tế và bằng chứng đã lọc dữ liệu.

Không ghi token, cookie, khóa workload hoặc dữ liệu người dùng thật vào artifact. ID tương quan và tham chiếu fixture thường đủ để nối sự kiện với trạng thái kiểm chứng.

| Kết luận dễ sai | Vì sao chưa đủ? |
| --- | --- |
| Không token thì bị từ chối nên đã cô lập tenant | Chưa kiểm tra danh tính hợp lệ của tenant khác |
| Request chéo tenant trả lỗi nên an toàn | Có thể endpoint hoặc fixture hỏng, hoặc tác động ghi đã xảy ra |
| Không thấy marker B trong trang đầu | Chưa bao phủ metadata, trang sau, export và các trường khác |
| Database tách riêng nên không cần test | Router, cache, worker và quyền quản trị vẫn có thể chọn nhầm nơi |
| Unit test policy đều pass | Chưa chứng minh điểm thực thi và nguồn tenant được nối đúng |
| Một lần chạy song song không lỗi | Chỉ là bằng chứng cho các lịch thực thi đã quan sát |

Nên phân tầng bằng test đơn vị cho quy tắc, test tích hợp cho truy vấn và context, rồi test đầu cuối cho những hành trình quan trọng. Khi một lỗi được phát hiện, thêm trường hợp hồi quy ở lớp có thể tái hiện và giải thích được nguyên nhân.

Tenant isolation test có giá trị khi chứng minh giới hạn được giữ trên toàn đường truy cập: từ danh tính đã xác thực, lựa chọn tenant và tài nguyên tới truy vấn, cache, worker và kết quả trả ra. Dữ liệu đọc đúng và việc không có tác động ghi trái phép cần được kiểm tra cùng nhau.
