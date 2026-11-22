# Hiểu giới hạn của tỷ lệ bao phủ mã và kết quả kiểm thử đạt

Một báo cáo kiểm thử có thể hiển thị 95% code coverage và tất cả test đều xanh, nhưng phần mềm vẫn có thể chứa lỗi nghiêm trọng. Có thể test đã chạy qua các dòng mã mà không kiểm tra kết quả đúng; nhánh xử lý lỗi chưa được thử; dữ liệu đầu vào chưa đại diện cho thực tế; hoặc các thành phần chỉ hoạt động sai khi kết hợp với nhau.

Tỷ lệ bao phủ mã (code coverage) cho biết một tập kiểm thử đã thực thi phần nào của mã nguồn theo cách đo của công cụ. Kết quả test đạt (passing test result) cho biết các trường hợp đã chạy không báo lỗi theo những điều kiện và kỳ vọng được khai báo. Hai tín hiệu này hữu ích để đánh giá phạm vi kiểm tra, nhưng không tự chứng minh test có chất lượng, yêu cầu nghiệp vụ đã được xác minh hay sản phẩm không còn lỗi.

Trong CI/CD, cần hiểu đúng giới hạn của hai tín hiệu này để thiết kế quality gate có ý nghĩa: đo những gì quan trọng, đọc kết quả trong bối cảnh rủi ro, kiểm tra chất lượng assertion và bổ sung các phương pháp như mutation testing, contract test hoặc kiểm thử theo thuộc tính khi phù hợp.

## 1. Code coverage đo điều gì?

Code coverage là phép đo mức độ mã được thực thi khi một tập test chạy. Công cụ thường instrument bytecode hoặc mã đã biên dịch, ghi nhận các vị trí được thực thi rồi tổng hợp thành báo cáo.

Ví dụ, một phương thức có mười dòng mã có thể được test thực thi tám dòng. Công cụ báo line coverage là 80% đối với phạm vi đó. Con số này cho biết có tám dòng được chạy ít nhất một lần theo định nghĩa của công cụ; nó không cho biết test đã kiểm tra đúng kết quả của tám dòng đó hay chưa.

Một báo cáo coverage cần được đọc cùng với:

- Phạm vi source được đưa vào phép đo.
- Loại coverage đang sử dụng.
- Những package hoặc file bị loại trừ.
- Phiên bản công cụ và cách instrument.
- Tập test đã chạy và trạng thái của từng test.
- Các nhánh, điều kiện hoặc luồng quan trọng còn chưa được thực thi.

Coverage là dữ liệu về **việc thực thi mã**, không phải điểm số trực tiếp về chất lượng phần mềm.

### Các loại coverage thường gặp

| Loại coverage | Câu hỏi được trả lời | Giới hạn chính |
|---|---|---|
| Statement coverage | Những câu lệnh nào đã được thực thi? | Một câu lệnh chạy qua chưa chứng minh kết quả của nó được kiểm tra |
| Line coverage | Những dòng mã nào đã được chạy? | Một dòng có thể chứa nhiều biểu thức hoặc nhánh |
| Function/method coverage | Những hàm hoặc phương thức nào đã được gọi? | Gọi hàm không có nghĩa mọi hành vi bên trong đã được thử |
| Branch coverage | Các nhánh quyết định nào đã được đi qua? | Không bao phủ mọi tổ hợp điều kiện con |
| Condition coverage | Mỗi điều kiện boolean con đã nhận cả true và false chưa? | Không nhất thiết chứng minh từng điều kiện độc lập làm thay đổi kết quả quyết định |
| MC/DC | Mỗi điều kiện con có thể độc lập làm thay đổi kết quả quyết định hay không? | Cần thiết kế test kỹ hơn; thường dùng ở hệ thống có yêu cầu an toàn cao |
| Path coverage | Những đường đi nào qua chương trình đã được thực thi? | Số đường đi có thể tăng rất lớn hoặc vô hạn khi có vòng lặp |

Các công cụ không nhất thiết hỗ trợ mọi loại coverage hoặc định nghĩa chúng giống nhau. Hãy xem tài liệu của công cụ đang dùng trước khi so sánh số liệu giữa các dự án hoặc giữa các báo cáo.

### Statement và line coverage

Statement coverage đếm câu lệnh được thực thi. Line coverage đếm dòng được thực thi theo cách công cụ ánh xạ mã nguồn và bytecode. Hai chỉ số có thể khác nhau nếu một dòng chứa nhiều câu lệnh hoặc một câu lệnh trải qua nhiều dòng.

Ví dụ:

~~~java
if (amount > 0) applyDiscount(); else reject();
~~~

Một dòng có thể chứa cả điều kiện và hai hành động. Line coverage có thể báo dòng đã chạy khi chỉ một nhánh được thực thi. Vì vậy, line coverage cao không đảm bảo nhánh xử lý đã được kiểm tra đầy đủ.

### Branch coverage

Branch coverage đo các nhánh điều khiển mà công cụ nhận diện từ if/else hoặc switch. Với biểu thức phức hợp dùng short-circuit như && và ||, compiler có thể tạo nhiều nhánh điều khiển bên trong một quyết định. Vì vậy, số nhánh được tính và cách hiển thị phụ thuộc bytecode, compiler và công cụ coverage.

Dù đạt branch coverage theo định nghĩa của công cụ, bộ test vẫn không nhất thiết đã thử mọi tổ hợp đầu vào hoặc chứng minh từng điều kiện con độc lập làm thay đổi kết quả. Điều này đặc biệt quan trọng với biểu thức boolean có nhiều thành phần.

## 2. Ví dụ: coverage cao nhưng vẫn bỏ sót lỗi

Giả sử hệ thống tính giảm giá cho khách hàng thành viên khi giá trị đơn hàng đạt ngưỡng:

~~~java
public BigDecimal calculateDiscount(
        boolean isMember,
        BigDecimal total
) {
    if (isMember && total.compareTo(new BigDecimal("100")) >= 0) {
        return total.multiply(new BigDecimal("0.10"));
    }
    return BigDecimal.ZERO;
}
~~~

Một test yếu có thể chỉ gọi phương thức và không kiểm tra kết quả:

~~~java
@Test
void calculatesDiscount() {
    var policy = new DiscountPolicy();
    policy.calculateDiscount(true, new BigDecimal("120"));
    assertTrue(true);
}
~~~

Test này có thể chạy qua nhánh cấp giảm giá và góp phần làm coverage tăng. Nhưng assertion luôn đúng, nên test không phát hiện được nếu phương thức trả về 0, trả sai tỷ lệ hoặc dùng nhầm ngưỡng.

Một test có giá trị hơn phải kiểm tra kết quả kỳ vọng:

~~~java
@Test
void memberWithEligibleOrderReceivesTenPercent() {
    var policy = new DiscountPolicy();

    var actual = policy.calculateDiscount(
        true,
        new BigDecimal("120")
    );

    assertEquals(new BigDecimal("12.00"), actual);
}
~~~

Vẫn cần thêm test cho khách không phải thành viên và đơn hàng dưới ngưỡng:

~~~java
@Test
void nonMemberDoesNotReceiveDiscount() {
    var policy = new DiscountPolicy();

    var actual = policy.calculateDiscount(
        false,
        new BigDecimal("120")
    );

    assertEquals(BigDecimal.ZERO, actual);
}

@Test
void memberBelowThresholdDoesNotReceiveDiscount() {
    var policy = new DiscountPolicy();

    var actual = policy.calculateDiscount(
        true,
        new BigDecimal("80")
    );

    assertEquals(BigDecimal.ZERO, actual);
}
~~~

Các test này kiểm tra những hành vi khác nhau. Chúng giúp phát hiện lỗi ở điều kiện thành viên, ngưỡng giá trị và kết quả tính toán. Coverage có thể vẫn bằng nhau giữa hai bộ test, nhưng chất lượng assertion khác nhau rõ rệt.

## 3. Branch coverage chưa đủ cho điều kiện phức hợp

Xét điều kiện:

~~~java
if (isMember && total >= threshold) {
    grantDiscount();
}
~~~

Có hai điều kiện con: isMember và total >= threshold. Để chứng minh từng điều kiện con có thể độc lập làm thay đổi quyết định, có thể dùng các trường hợp sau:

| Test | isMember | total >= threshold | Kết quả quyết định |
|---|---:|---:|---:|
| A | true | true | true |
| B | false | true | false |
| C | true | false | false |

Ở cặp A và B, điều kiện isMember thay đổi trong khi điều kiện ngưỡng giữ true; kết quả quyết định thay đổi. Ở cặp A và C, điều kiện ngưỡng thay đổi trong khi isMember giữ true; kết quả cũng thay đổi. Đây là ý tưởng của Modified Condition/Decision Coverage (MC/DC).

MC/DC hữu ích trong các hệ thống có yêu cầu an toàn hoặc quy định nghiêm ngặt. Với ứng dụng thông thường, không phải mọi module đều cần MC/DC; nhóm nên chọn mức kiểm tra theo rủi ro và hậu quả của lỗi.

### Path coverage có giới hạn thực tế

Path coverage cố gắng đo các đường đi qua chương trình. Với nhiều nhánh và vòng lặp, số đường đi tăng nhanh. Một vòng lặp có thể chạy 0, 1, 2 hoặc nhiều lần; nếu số lần lặp không giới hạn thì số đường đi tiềm năng cũng không hữu hạn.

Do đó, thay vì cố đạt 100% path coverage cho toàn bộ hệ thống, thường nên chọn:

- Các luồng nghiệp vụ quan trọng.
- Các đường đi liên quan tới lỗi đã từng xảy ra.
- Các tổ hợp điều kiện có rủi ro cao.
- Các biên đầu vào và trạng thái chuyển tiếp.
- Các luồng lỗi, timeout, retry và phục hồi.

## 4. Vì sao 100% coverage không có nghĩa không còn lỗi?

Một chương trình có thể được thực thi 100% dòng mã nhưng test vẫn không phát hiện lỗi. Có nhiều nguyên nhân:

### Test chỉ chạy mã mà không kiểm tra hành vi

Test gọi hàm, đi qua nhánh và kết thúc mà không có assertion có ý nghĩa. Coverage ghi nhận mã đã chạy, nhưng không đánh giá kỳ vọng của người viết test.

### Assertion quá yếu

Ví dụ:

~~~java
assertNotNull(result);
assertTrue(result >= 0);
~~~

Hai assertion này có thể chấp nhận nhiều kết quả sai. Nếu yêu cầu là giảm giá chính xác 10%, test cần kiểm tra giá trị hoặc quy tắc tương ứng.

### Test kiểm tra cùng logic với implementation

Nếu test tự tính expected bằng cách gọi lại cùng hàm hoặc sao chép nguyên công thức từ implementation, cùng một lỗi có thể xuất hiện ở cả hai nơi. Khi đó test không còn là nguồn xác minh độc lập.

Expected result nên đến từ đặc tả, ví dụ nghiệp vụ, bảng dữ liệu chuẩn hoặc một oracle độc lập phù hợp.

### Chỉ kiểm tra trường hợp thuận lợi

Một hàm có thể có coverage cao khi test chỉ dùng dữ liệu hợp lệ. Các trường hợp null, rỗng, biên, vượt giới hạn, dữ liệu sai định dạng hoặc trạng thái không mong muốn vẫn có thể chưa được kiểm tra.

### Không kiểm tra tương tác giữa các thành phần

Unit test có thể chứng minh từng lớp hoạt động khi mock dependency, nhưng không chứng minh database schema, serialization, message broker, API contract hoặc cấu hình triển khai thực tế tương thích.

### Bỏ sót concurrency và trạng thái thời gian

Test chạy tuần tự có thể không phát hiện race condition, deadlock, lỗi đồng bộ hoặc vấn đề chỉ xảy ra khi nhiều request đồng thời. Những lỗi phụ thuộc thời gian, retry, timeout hoặc thứ tự sự kiện cũng khó phát hiện bằng coverage đơn thuần.

### Test không đại diện cho môi trường thật

Test có thể chạy với JDK, database, locale, timezone hoặc cấu hình khác production. Coverage cao trong môi trường giả lập không chứng minh hành vi tương tự trong môi trường triển khai.

## 5. Kết quả test đạt chứng minh điều gì?

Khi pipeline báo test passed, cách diễn giải chính xác là: **các test được thực thi đã hoàn tất mà không vi phạm những điều kiện thất bại được khai báo trong lần chạy đó**.

Kết quả này phụ thuộc vào chất lượng của:

- Danh sách test thực sự được chạy.
- Assertion và test oracle.
- Dữ liệu đầu vào.
- Môi trường và dependency.
- Cấu hình test runner.
- Những test bị skip, disable hoặc quarantine.
- Quy tắc xử lý retry và lỗi của pipeline.

Một trạng thái xanh không tự chứng minh mọi test đã chạy. Cần kiểm tra số lượng test discovered, executed, passed, failed, skipped và aborted.

### Các trường hợp có thể tạo cảm giác xanh giả

| Tình huống | Vì sao kết quả gây hiểu nhầm | Cách kiểm tra |
|---|---|---|
| Không tìm thấy test | Một task có thể kết thúc mà không thực thi test mong muốn | Xác nhận số test được phát hiện và cấu hình fail khi không có test |
| Test bị skip hoặc disable | Luồng quan trọng không được thực thi | Báo cáo skipped và review lý do |
| Job cho phép failure | Test lỗi nhưng pipeline vẫn tiếp tục | Xem allow_failure, continue-on-error và required checks |
| Retry che lỗi chập chờn | Lần chạy sau xanh dù lần đầu thất bại | Lưu lịch sử retry và tỷ lệ flaky |
| Test chỉ kiểm tra mock | Hợp đồng với hệ thống thật chưa được xác minh | Bổ sung integration hoặc contract test |
| Assertion không kiểm tra kết quả | Test chạy qua nhưng không phát hiện sai hành vi | Review assertion và expected result |
| Dùng dữ liệu cố định quá đơn giản | Không phản ánh dữ liệu thực tế hoặc trường hợp biên | Bổ sung boundary và representative data |
| Chạy nhầm test suite | Pipeline xanh nhưng thiếu lớp kiểm thử bắt buộc | Kiểm tra task graph, test filter và report |

### Test đạt không đồng nghĩa yêu cầu đã được bao phủ

Một yêu cầu nghiệp vụ có thể liên quan nhiều hành vi và điều kiện. Test có thể đạt coverage cao nhưng vẫn bỏ sót một yêu cầu không được chuyển thành test case.

Nhóm nên liên kết yêu cầu, rủi ro và test case quan trọng. Ví dụ, với chức năng thanh toán, cần kiểm tra cả giao dịch thành công, từ chối, timeout, gửi lặp, hoàn tiền và tính nhất quán trạng thái. Chỉ kiểm tra phương thức xử lý thanh toán đã được gọi không đủ chứng minh toàn bộ luồng nghiệp vụ.

## 6. Phân biệt code coverage, test coverage và requirements coverage

Các thuật ngữ này thường bị dùng thay thế cho nhau, nhưng đo những thứ khác nhau:

| Khái niệm | Đối tượng được đo | Ví dụ câu hỏi |
|---|---|---|
| Code coverage | Mã nguồn được thực thi | Dòng, nhánh hoặc phương thức nào đã chạy? |
| Test coverage theo phạm vi chức năng | Tính năng hoặc thành phần có test | Các module hoặc luồng chức năng nào đã có test? |
| Requirements coverage | Yêu cầu được liên kết với test | Mỗi yêu cầu quan trọng có test xác minh chưa? |
| Risk coverage | Rủi ro được kiểm tra | Các lỗi có hậu quả lớn đã có biện pháp phát hiện chưa? |
| Mutation score | Khả năng test phát hiện thay đổi sai có chủ đích | Test có thất bại khi hành vi bị thay đổi nhỏ không? |

Một dự án có thể có code coverage 90% nhưng requirements coverage thấp nếu nhiều yêu cầu quan trọng chưa được kiểm tra. Ngược lại, một module có code coverage thấp hơn nhưng các rủi ro trọng yếu đã được kiểm thử kỹ có thể đáng tin cậy hơn trong phạm vi đã xác định.

Không nên dùng một chỉ số để đại diện cho mọi chiều chất lượng.

## 7. Đọc coverage report đúng cách

Khi xem báo cáo, đừng chỉ nhìn tổng phần trăm. Hãy kiểm tra:

1. Phạm vi source được đưa vào báo cáo có đúng với module đang đánh giá không?
2. File nào bị loại trừ và lý do có hợp lý không?
3. Branch coverage có thấp hơn line coverage đáng kể không?
4. Các lớp xử lý lỗi, phân quyền, tiền tệ hoặc trạng thái quan trọng có được kiểm tra không?
5. Có file mới hoặc thay đổi lớn chưa có test không?
6. Báo cáo có được tạo từ đúng test suite và đúng commit không?
7. Test bị skip, ignore hoặc disable có được hiển thị không?

### Đừng để exclusions làm đẹp con số

Một số file được loại khỏi coverage là hợp lý, chẳng hạn mã sinh tự động, lớp cấu hình thuần túy hoặc mã không thể kiểm thử theo cách thông thường. Tuy nhiên, nếu loại trừ quá nhiều file nghiệp vụ, tỷ lệ coverage có thể tăng mà mức xác minh thực tế không thay đổi.

Mọi exclusion nên có lý do, phạm vi rõ và được review. Nên theo dõi cả tỷ lệ coverage và danh sách file bị loại trừ qua thời gian.

### Tổng coverage có thể che giấu module yếu

Giả sử một hệ thống có ba module:

| Module | Coverage |
|---|---:|
| Common utilities | 98% |
| Reporting | 95% |
| Payment | 42% |
| Tổng toàn hệ thống | 88% |

Con số tổng 88% có thể tạo cảm giác tốt, nhưng module Payment có rủi ro cao lại chỉ đạt 42%. Vì vậy, cần đọc coverage theo module, package hoặc thành phần quan trọng, không chỉ theo một con số tổng.

## 8. Mutation testing: kiểm tra xem test có phát hiện lỗi hay không

Mutation testing tạo ra những thay đổi nhỏ có chủ đích trong mã nguồn để xem test có phát hiện được hay không. Các thay đổi đó gọi là mutant.

Ví dụ:

- Đổi > thành >=.
- Đổi && thành ||.
- Thay một giá trị trả về bằng giá trị khác.
- Xóa một lời gọi kiểm tra.
- Đảo điều kiện true/false.

Nếu test thất bại khi mutant được áp dụng, mutant bị "killed". Nếu test vẫn xanh, mutant "survived", có thể test chưa kiểm tra hành vi bị thay đổi hoặc mutant không ảnh hưởng tới luồng được chạy.

### Ví dụ

Mã ban đầu:

~~~java
if (total >= threshold) {
    grantDiscount();
}
~~~

Mutant:

~~~java
if (total > threshold) {
    grantDiscount();
}
~~~

Nếu test chỉ dùng total = 150 và threshold = 100, cả hai phiên bản đều cho cùng kết quả. Mutant sống sót. Một test ở đúng biên total = threshold mới phát hiện sự khác biệt.

### Mutation score

Một cách tính thường dùng:

~~~text
Mutation score = (Mutants killed / Mutants considered) * 100%
~~~

Các công cụ có thể loại mutant tương đương (equivalent mutant) hoặc mutant không thể thực thi khỏi mẫu số. Vì cách xử lý khác nhau, cần đọc định nghĩa score của công cụ trước khi so sánh.

Mutation score giúp đánh giá khả năng phát hiện lỗi của test, nhưng không phải thước đo tuyệt đối. Mutation testing có thể tốn thời gian, phụ thuộc tập toán tử mutation và không mô phỏng mọi loại lỗi thực tế. Nên áp dụng cho module quan trọng, logic nghiệp vụ phức tạp hoặc các vùng mà test thường xuyên bỏ sót lỗi.

## 9. Kết hợp coverage với test oracle và các kỹ thuật kiểm thử khác

Một test tốt cần có test oracle: cơ sở để xác định kết quả đúng. Oracle có thể là giá trị kỳ vọng, invariant, hợp đồng API, quy tắc nghiệp vụ hoặc dữ liệu chuẩn độc lập.

### Example-based testing

Kiểm tra các trường hợp đầu vào cụ thể và kết quả mong đợi. Phù hợp với quy tắc nghiệp vụ rõ ràng, các trường hợp biên và lỗi từng xuất hiện.

### Boundary-value testing

Tập trung vào biên của miền dữ liệu: 0, 1, giá trị tối đa, ngay dưới ngưỡng, đúng ngưỡng và ngay trên ngưỡng. Lỗi thường xuất hiện tại các phép so sánh, giới hạn và chuyển trạng thái.

### Property-based testing

Thay vì chỉ liệt kê một vài ví dụ, test tạo nhiều đầu vào và xác minh một thuộc tính phải luôn đúng. Ví dụ, tổng tiền sau khi áp dụng chiết khấu không được âm; sắp xếp một danh sách rồi sắp xếp lại lần nữa không làm thay đổi kết quả.

Cần lưu seed hoặc thông tin đầu vào khi test thất bại để có thể tái hiện lỗi. Test ngẫu nhiên không có khả năng tái hiện sẽ khó dùng trong CI.

### Contract và integration testing

Contract test xác minh các thành phần tuân thủ hợp đồng giao tiếp. Integration test kiểm tra tương tác thực tế giữa module hoặc với hệ thống phụ trợ như database, broker và filesystem.

Các test này bổ sung cho unit test vì nhiều lỗi chỉ xuất hiện tại ranh giới thành phần.

### End-to-end testing

E2E test xác minh luồng nghiệp vụ qua nhiều lớp gần với cách người dùng hoặc hệ thống bên ngoài sử dụng. Chúng có giá trị với hành vi xuyên suốt, nhưng thường tốn thời gian và dễ chịu ảnh hưởng từ môi trường. Nên chọn luồng quan trọng thay vì cố đưa mọi trường hợp vào E2E.

## 10. Đặt quality gate cho coverage có ý nghĩa

Coverage gate là điều kiện chất lượng dựa trên báo cáo coverage. Gate hữu ích khi được dùng để ngăn giảm chất lượng và hướng sự chú ý vào vùng mã có rủi ro.

### Không có một ngưỡng phù hợp cho mọi dự án

Ngưỡng 80% hoặc 90% không tự động là tốt. Một thư viện xử lý tài chính có thể cần kiểm tra branch và boundary chặt hơn một module chuyển đổi dữ liệu đơn giản. Một module mới có thể đặt mục tiêu cao hơn module legacy khó kiểm thử.

Khi chọn ngưỡng, xem xét:

- Mức độ quan trọng của chức năng.
- Hậu quả nếu có lỗi.
- Độ phức tạp và số nhánh logic.
- Mức độ thay đổi của module.
- Khả năng kiểm thử tự động.
- Lịch sử lỗi và sự cố.
- Chi phí duy trì test.

### Kết hợp ngưỡng tổng thể và coverage của mã mới

Một hệ thống legacy có thể bắt đầu ở mức coverage thấp. Nếu bắt buộc nâng toàn bộ hệ thống lên một ngưỡng cao trong một lần, nhóm có thể phải tạo nhiều test ít giá trị chỉ để đạt con số.

Có thể áp dụng hai quy tắc:

- Không cho coverage tổng thể giảm dưới baseline đã thống nhất.
- Mã mới hoặc mã thay đổi phải đáp ứng ngưỡng phù hợp với rủi ro.

Diff coverage giúp tập trung vào phần thay đổi trong PR. Tuy nhiên, nó không thay thế việc kiểm tra module hoặc luồng phụ thuộc mà thay đổi đó có thể ảnh hưởng.

### Gate cần kiểm tra cả tính hợp lệ của báo cáo

Một quality gate nên thất bại nếu:

- Báo cáo coverage không được tạo.
- Không có test nào chạy dù suite bắt buộc phải có test.
- Có test bắt buộc bị bỏ qua ngoài chính sách.
- Coverage giảm dưới ngưỡng đã định.
- Một vùng rủi ro cao chưa có test bắt buộc.
- Kết quả coverage không gắn với commit hoặc test run hiện tại.

Ngoại lệ cần có lý do và thời hạn xử lý. Không nên âm thầm loại file hoặc giảm ngưỡng chỉ để pipeline xanh.

## 11. Ví dụ cấu hình JaCoCo trong Gradle

JaCoCo là công cụ phổ biến để đo coverage cho ứng dụng Java. Ví dụ Kotlin DSL sau tạo báo cáo và đặt gate branch coverage cho toàn bộ bundle.

~~~kotlin
plugins {
    java
    jacoco
}

tasks.test {
    useJUnitPlatform()
    finalizedBy(tasks.jacocoTestReport)
}

tasks.jacocoTestReport {
    dependsOn(tasks.test)
    reports {
        xml.required.set(true)
        html.required.set(true)
    }
}

tasks.jacocoTestCoverageVerification {
    dependsOn(tasks.test)

    violationRules {
        rule {
            element = "BUNDLE"
            limit {
                counter = "BRANCH"
                value = "COVEREDRATIO"
                minimum = "0.75".toBigDecimal()
            }
        }
    }
}

tasks.check {
    dependsOn(tasks.jacocoTestCoverageVerification)
}
~~~

Trong ví dụ, ngưỡng 75% chỉ minh họa cách cấu hình. Dự án cần chọn ngưỡng dựa trên rủi ro và baseline thực tế.

Một số lưu ý:

- JaCoCo có thể báo cáo instruction, branch, line, complexity, method và class coverage.
- Branch coverage của JaCoCo tập trung vào nhánh của if và switch; không nên xem nó như MC/DC.
- Cần cấu hình source set, test task và exclusions chính xác.
- Nếu có nhiều test task hoặc nhiều module, phải tổng hợp report đúng phạm vi.
- Gate phải chạy trên report mới nhất của commit hiện tại.
- Nên lưu XML report để nền tảng CI hoặc công cụ phân tích khác đọc được.

## 12. Đọc kết quả test trong CI/CD

Một pipeline đáng tin cậy cần công bố kết quả test đủ chi tiết để người review hiểu trạng thái thật.

Báo cáo tối thiểu nên thể hiện:

| Trường | Ý nghĩa |
|---|---|
| Tests discovered | Số test runner phát hiện |
| Tests executed | Số test thực sự được thực thi |
| Passed | Số test hoàn tất đúng |
| Failed | Số test không đạt |
| Skipped/disabled | Số test không chạy theo cấu hình |
| Aborted/cancelled | Số test bị dừng giữa chừng |
| Duration | Thời gian chạy |
| Retry history | Test nào phải chạy lại và kết quả từng lần |
| Coverage | Coverage gắn với đúng test run |
| Commit/build ID | Phiên bản source được kiểm tra |

Không nên chỉ đọc biểu tượng xanh hoặc đỏ. Khi một job xanh nhưng số test executed bằng 0, cần xem đó là kết quả bất thường và xác minh cấu hình.

### Flaky test

Flaky test là test có thể cho kết quả khác nhau khi chạy lại với cùng mã nguồn và điều kiện tưởng như giống nhau. Nguyên nhân có thể là thời gian, concurrency, thứ tự test, dữ liệu dùng chung, network hoặc phụ thuộc môi trường.

Một test flaky làm giảm niềm tin vào kết quả CI. Retry có thể giúp phân biệt lỗi tạm thời, nhưng không nên coi lần retry thành công là bằng chứng test ổn định. Cần ghi lại lần chạy đầu, retry, tần suất và điều kiện tái hiện rồi sửa nguyên nhân gốc.

### Test bị skip và quarantine

Có thể tạm quarantine một test flaky để bảo vệ nhịp CI, nhưng cần:

- Ghi rõ lý do.
- Giao người chịu trách nhiệm.
- Theo dõi thời hạn khắc phục.
- Không tính test quarantine như test đã xác minh hành vi.
- Không để các test quan trọng bị bỏ qua vô thời hạn.

## 13. Ví dụ đánh giá một PR

Giả sử PR thay đổi logic tính phí:

- Line coverage tổng của module tăng từ 82% lên 85%.
- Branch coverage của module là 68%.
- Tất cả 120 test được báo passed.
- Có 4 test bị skip.
- Phần mã mới đạt diff coverage 100%.

Không nên kết luận PR an toàn chỉ từ các con số này. Reviewer cần hỏi thêm:

1. Bốn test bị skip có liên quan tới logic tính phí hoặc môi trường tích hợp không?
2. Test mới có kiểm tra giá trị phí chính xác hay chỉ xác nhận phương thức không ném exception?
3. Có test cho giá trị biên, số âm, làm tròn, tiền tệ và điều kiện miễn phí không?
4. Branch chưa được bao phủ có liên quan tới xử lý lỗi hoặc quyền truy cập không?
5. Test có sử dụng database hoặc contract thật ở những ranh giới cần xác minh không?
6. Báo cáo có được tạo từ đúng commit và đúng test suite không?

Nếu các câu hỏi quan trọng chưa được trả lời, PR cần bổ sung kiểm thử dù coverage tổng đang cao. Nếu bốn test bị skip là các test môi trường không áp dụng cho job hiện tại, cần thể hiện rõ trong báo cáo và có một job khác thực hiện chúng ở giai đoạn phù hợp.

## 14. Những cách sử dụng coverage sai

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Đặt mục tiêu 100% cho mọi module | Khuyến khích test hình thức và tăng chi phí bảo trì | Đặt mục tiêu theo rủi ro và loại coverage |
| Chỉ xem line coverage | Bỏ qua nhánh và điều kiện quan trọng | Xem branch, condition và luồng nghiệp vụ |
| Viết assertion luôn đúng | Coverage tăng nhưng test không phát hiện lỗi | Kiểm tra expected result cụ thể |
| Exclude file để tăng phần trăm | Số liệu đẹp nhưng phạm vi kiểm tra giảm | Review và quản lý exclusions |
| Dùng coverage tổng làm đại diện | Module rủi ro cao có thể bị che bởi module khác | Theo dõi theo module/package |
| Retry test đến khi xanh | Che giấu flaky test | Ghi nhận retry và sửa nguyên nhân |
| Coi skipped như passed | Test bắt buộc không được thực thi | Báo cáo trạng thái riêng và gate rõ |
| Mock mọi dependency | Không phát hiện lỗi tích hợp | Bổ sung contract và integration test |
| Tăng coverage bằng test getter/setter hàng loạt | Tốn công mà ít tăng khả năng phát hiện lỗi | Ưu tiên logic, nhánh và rủi ro |
| Dùng cùng logic để tạo expected | Lỗi có thể lặp lại trong test | Dùng oracle độc lập hoặc dữ liệu chuẩn |
| Đặt ngưỡng mà không có baseline | Khó đánh giá tiến bộ và dễ phá pipeline | Thiết lập baseline rồi tăng dần |

## 15. Checklist đánh giá chất lượng kiểm thử

### Đối với coverage

- [ ] Biết rõ báo cáo đang dùng line, branch hay loại coverage nào.
- [ ] Phạm vi source và exclusions được review.
- [ ] Coverage được xem theo module và vùng rủi ro.
- [ ] Các nhánh xử lý lỗi, quyền và biên dữ liệu quan trọng có test.
- [ ] Không dùng một tỷ lệ tổng để kết luận toàn hệ thống an toàn.
- [ ] Mã mới được đánh giá bằng diff coverage khi phù hợp.
- [ ] Ngưỡng gate có baseline, lý do và quy tắc ngoại lệ.

### Đối với kết quả test

- [ ] Test runner phát hiện đúng số lượng test mong đợi.
- [ ] Test bắt buộc thực sự được thực thi.
- [ ] Passed, failed, skipped, aborted và retry được báo cáo riêng.
- [ ] Assertion kiểm tra hành vi và kết quả có ý nghĩa.
- [ ] Test oracle độc lập với implementation.
- [ ] Có trường hợp biên, dữ liệu không hợp lệ và luồng lỗi.
- [ ] Contract/integration test được dùng ở ranh giới cần thiết.
- [ ] Flaky test được theo dõi và xử lý.
- [ ] Test chạy trên phiên bản source và môi trường được xác định.

### Đối với quality gate

- [ ] Coverage report được tạo và gắn với commit hiện tại.
- [ ] Gate không chấp nhận report thiếu hoặc test suite rỗng ngoài dự kiến.
- [ ] Ngưỡng được chọn theo rủi ro thay vì chạy theo con số chung.
- [ ] Test thất bại hoặc bị skip trái chính sách sẽ chặn merge/phát hành.
- [ ] Ngoại lệ có lý do, người chịu trách nhiệm và thời hạn.
- [ ] Các module quan trọng có thêm kiểm tra phù hợp ngoài coverage.

## Kết luận

Code coverage cho biết test đã thực thi phần nào của mã; kết quả test đạt cho biết các trường hợp được chạy đã thỏa mãn những kỳ vọng được khai báo. Cả hai đều là tín hiệu hữu ích nhưng không chứng minh test đủ sâu hoặc phần mềm không còn lỗi. Hãy kết hợp coverage với assertion có ý nghĩa, test oracle độc lập, kiểm thử biên, mutation testing, contract/integration test và đánh giá theo rủi ro. Một quality gate tốt giúp nhóm hiểu chính xác điều gì đã được kiểm tra, điều gì còn bỏ ngỏ và vì sao một thay đổi được phép đi tiếp trong pipeline CI/CD.

