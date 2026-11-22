# Kiểm thử invariant — Invariant testing

## 1. Kiểm thử điều phải luôn được giữ

Một ca kiểm thử như “tạo đơn thành công” chỉ chứng minh một đường đi cụ thể cho kết quả mong đợi. Nó chưa chứng minh hệ thống không bán vượt tồn kho, không hoàn tiền hai lần hoặc không cho người dùng thao tác trên đối tượng ngoài quyền.

**Invariant** là thuộc tính phải được giữ trong phạm vi và tại những mốc đã xác định. **Invariant testing** là kiểm thử các thao tác, chuỗi thao tác và tình huống lỗi để tìm trạng thái hoặc lịch sử vi phạm thuộc tính đó.

Trong chương **Security Invariants** của học phần **Business Logic Security**, kiểm thử cần nối trực tiếp với tài sản và kết quả bị cấm. Các cơ chế như quyền theo đối tượng, state machine, transaction và idempotency phải được đánh giá bằng thuộc tính chúng bảo vệ.

Ví dụ:

~~~text
Không chấp nhận tổng quyền chi mới vượt tiền khả dụng.
Không giữ hoặc bán nhiều đơn vị hơn khả năng cấp.
Không thực thi nội dung khác với nội dung đã được phê duyệt.
Không tạo tác động thứ hai từ cùng một quyết định chỉ dùng một lần.
Không cho actor ngoài quyền làm thay đổi tài sản của chủ thể khác.
~~~

Mục tiêu không phải chỉ đếm số test. Mục tiêu là tìm cách làm những điều này sai và lưu được bằng chứng về phạm vi đã kiểm chứng.

Sau bài này, bạn cần có khả năng:

- Viết invariant đủ chính xác để kiểm tra bằng máy.
- Xây dựng oracle không phụ thuộc hoàn toàn vào cùng logic đang được kiểm thử.
- Thiết kế ca tuần tự, chuỗi sinh tự động, cạnh tranh và lỗi từng phần.
- Phân biệt thuộc tính của trạng thái, chuyển trạng thái và tác động theo thời gian.
- Đọc kết quả kiểm thử mà không suy diễn vượt quá bằng chứng.

## 2. Viết rõ thuộc tính, phạm vi và mốc quan sát

Một invariant tốt không chỉ có công thức. Nó cần nói rõ công thức áp dụng cho đối tượng nào, với dữ liệu nào và vào lúc nào.

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Tài sản | Điều gì cần được giữ? | Số đơn vị có thể giữ hoặc bán |
| Phạm vi | Theo tenant, tài khoản, payment hay SKU nào? | Một SKU tại một kho của một tenant |
| Nguồn có thẩm quyền | Dữ kiện lấy từ đâu? | Bản ghi tồn và các khoản giữ đã commit |
| Thuộc tính | Điều gì không được sai? | Tổng đang giữ và đã bán không vượt khả năng cấp |
| Mốc quan sát | Khi nào cần đúng? | Sau mỗi transaction nghiệp vụ đã commit |
| Ngoại lệ | Có thao tác hợp lệ làm thay đổi giả định không? | Nhập hàng hoặc điều chỉnh được phê duyệt |
| Dấu hiệu vi phạm | Kiểm thử quan sát điều gì? | Số âm, tổng lệch, tác động trùng hoặc chuyển trạng thái sai |

Câu “số dư luôn không âm” có thể sai với sản phẩm có tín dụng hoặc phải phản ánh một khoản đảo giao dịch đã xảy ra. Cần xác định đúng mô hình trước khi biến một khẩu hiệu thành assertion.

Tương tự, tổng số hàng chỉ bất biến trong một phạm vi đóng không có nhập, trả hoặc điều chỉnh ngoài mô hình. Nếu có những thao tác đó, phải đưa chúng vào phương trình và oracle.

### 2.1. Ba loại thuộc tính thường gặp

| Loại | Ví dụ | Cách kiểm tra chính |
| --- | --- | --- |
| Trạng thái | Đang giữ + đã bán không vượt khả năng cấp | Đọc snapshot nhất quán và tính lại |
| Chuyển trạng thái | Khoản giữ đã giải phóng không được xác nhận bán | So trạng thái nguồn, hành động và kết quả |
| Lịch sử hoặc số lần tác động | Một xác nhận không tạo hai lệnh giao hàng | Theo dõi định danh và tác động xuyên các lần retry |

Một snapshot cuối có thể hợp lệ dù đã có tác động sai trước đó. Ví dụ, số dư được điều chỉnh lại không xóa việc tiền từng chuyển hai lần. Vì vậy, một số invariant cần kiểm tra lịch sử và hệ thống nhận tác động, không chỉ cột hiện tại.

### 2.2. Phân biệt precondition, postcondition và invariant

- **Precondition:** điều kiện để hành động được phép, như lượng giữ mới phải dương.
- **Postcondition:** quan hệ mong đợi sau một lần hành động, như giữ thành công 3 đơn vị làm lượng đang giữ tăng 3.
- **Invariant:** thuộc tính vẫn phải đúng qua mọi hành động trong mô hình, như không cấp quá khả năng.

Kiểm thử cần cả ba. Một hệ thống có thể không bao giờ vượt tồn vì từ chối mọi request, nhưng vẫn sai chức năng. Ngược lại, nhiều request hợp lệ riêng lẻ có thể tạo tổng trạng thái sai khi phối hợp.

Với request bị từ chối, cần xác định phần trạng thái nghiệp vụ nào không được đổi. Việc thêm log hoặc audit hợp lệ không nhất thiết là vi phạm “không có tác động”. Trong kiểm thử có nhiều luồng, thay đổi do request khác cũng phải được phân biệt, không so hai snapshot rồi quy mọi khác biệt cho request bị từ chối.

## 3. Ví dụ xuyên suốt: giữ và xác nhận tồn kho

Xét một mô hình minh họa cho một SKU của tenant T1:

- Khả năng cấp ban đầu là K = 10 đơn vị.
- A là số còn khả dụng.
- H là tổng lượng đang giữ.
- S là tổng lượng đã được xác nhận bán trong mô hình.
- Mỗi khoản giữ có số lượng dương, chủ sở hữu và trạng thái.
- Không có nhập hàng, trả lại hoặc điều chỉnh khả năng cấp trong kịch bản cơ sở.
- Xác nhận bán ở đây là cam kết nghiệp vụ, không tự chứng minh hàng đã được giao vật lý.

Các invariant:

~~~text
K >= 0
A >= 0
H >= 0
S >= 0

A + H + S = K

H = tổng số lượng của các hold đang ACTIVE
S = tổng số lượng của các hold đã CONFIRMED
~~~

Các phép tổng chỉ tính đúng tenant, kho, SKU và phạm vi đang kiểm thử.

### 3.1. Các chuyển trạng thái

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE: Giữ thành công lượng q
    ACTIVE --> CONFIRMED: Xác nhận bán
    ACTIVE --> RELEASED: Hủy hoặc hết hạn theo chính sách
~~~

Trong mô hình cơ sở, một hold không đi từ RELEASED sang CONFIRMED và không xác nhận hai lần. Nếu sản phẩm hỗ trợ xác nhận một phần, hoàn tác bán hoặc cấp lại, cần mô hình bổ sung phần còn lại và các điều kiện tương ứng.

| Thao tác | Điều kiện | Thay đổi mong đợi |
| --- | --- | --- |
| Giữ q | q > 0, q <= A, actor và đối tượng hợp lệ | A giảm q, H tăng q |
| Xác nhận hold q | ACTIVE, đủ điều kiện và đúng quyền | H giảm q, S tăng q, A không đổi |
| Giải phóng hold q | ACTIVE, đúng quyền hoặc đúng tác vụ hết hạn | H giảm q, A tăng q |
| Retry cùng ý định | Đúng hợp đồng idempotency và quyền đọc kết quả | Không nhân thêm khoản giữ hoặc tác động |
| Thao tác bị cấm | Sai quyền, sai trạng thái hoặc vượt khả dụng | Không tạo thay đổi nghiệp vụ bị cấm |

### 3.2. Một chuỗi tuần tự hợp lệ

~~~text
Ban đầu:           A=10, H=0, S=0
Giữ 3:             A=7, H=3, S=0
Giữ thêm 2:        A=5, H=5, S=0
Xác nhận hold 3:   A=5, H=2, S=3
Giải phóng hold 2: A=7, H=0, S=3
~~~

Tổng luôn bằng 10. Tuy nhiên, kiểm tra tổng chưa đủ. Một lỗi có thể làm A giảm sai và S tăng sai nhưng tổng vẫn bằng 10. Cần kiểm tra cả ý nghĩa từng thao tác, trạng thái hold, chủ sở hữu và nguồn của các tổng.

## 4. Xây dựng oracle độc lập đủ để phát hiện lỗi

**Oracle** là cơ chế quyết định kết quả quan sát có đúng hay không. Nếu oracle gọi lại chính hàm nghiệp vụ đang lỗi rồi so với response, test có thể chỉ xác nhận hai nơi cùng dùng một sai sót.

Ví dụ, production tính H bằng một bộ đếm. Oracle có thể đọc riêng các hold đã commit và tính tổng lượng ACTIVE, rồi so với bộ đếm đó. Nếu cả test lẫn production đều chỉ đọc cùng cột H, lỗi làm lệch cột với hold sẽ không bị phát hiện.

### 4.1. Các nguồn bằng chứng nên được đối chiếu

| Nguồn | Có thể kiểm tra điều gì? | Giới hạn |
| --- | --- | --- |
| Response | Hợp đồng API và định danh được trả | Có thể không phản ánh tác động đã commit khi mất phản hồi |
| Trạng thái có thẩm quyền | Số lượng, trạng thái và phiên bản hiện tại | Không luôn cho thấy tác động sai đã được bù trước đó |
| Hold hoặc sổ chi tiết | Tái dựng các tổng và quan hệ | Cần biết đầy đủ phạm vi và ngữ nghĩa trạng thái |
| Outbox và lệnh | Số ý định tác động đã được tạo | Không tự chứng minh số lần bên ngoài thực hiện |
| Nhà cung cấp mô phỏng hoặc đối soát | Tác động thực tế được ghi nhận ở bên nhận | Phải mô phỏng đúng các khả năng cần kiểm tra |
| Mô hình tham chiếu | Kết quả kỳ vọng từ các thao tác trừu tượng | Có thể sai hoặc thiếu chính sách nếu thiết kế kém |

Không có nguồn đơn lẻ nào luôn đủ. Cần chọn nguồn theo invariant.

### 4.2. Snapshot quan sát phải nhất quán

Nếu test đọc A, sau đó một transaction khác xác nhận hold, rồi test đọc H và S, nó có thể ghép các giá trị thuộc nhiều thời điểm thành một trạng thái chưa từng tồn tại.

Có thể quan sát tại điểm hệ thống đã dừng thay đổi có kiểm soát, hoặc dùng một cơ chế snapshot nhất quán phù hợp với cơ sở dữ liệu. Nếu nhiều dịch vụ tham gia, cần chỉ ra mốc quan sát và các thuộc tính cục bộ hoặc hội tụ tương ứng.

Không báo lỗi invariant chỉ từ một bộ dữ kiện ghép không nhất quán. Ngược lại, cũng không chỉ đợi mọi thứ được đối soát rồi bỏ qua vi phạm đã lộ ra ở một mốc cần đúng.

### 4.3. Số học của oracle cũng cần đúng

Tổng nhiều giá trị có thể tràn kiểu số dù từng giá trị riêng lẻ hợp lệ. Oracle có thể dùng kiểu rộng hoặc số nguyên độ dài tùy ý để tránh cùng lỗi tràn với production.

Luôn giữ đơn vị và phạm vi. Không cộng tiền khác tiền tệ hoặc số lượng khác SKU rồi coi tổng khớp là đủ.

## 5. Chọn tầng kiểm thử theo thuộc tính cần chứng minh

| Tầng | Phù hợp để kiểm tra | Không tự chứng minh |
| --- | --- | --- |
| Unit test của quy tắc | Miền giá trị, điều kiện và tính toán thuần | Khóa dữ liệu và cạnh tranh nhiều instance |
| Test mô hình domain | Chuỗi hành động và state machine | Tính nguyên tử của repository thật |
| Test tích hợp cơ sở dữ liệu | Transaction, constraint, rollback và tranh chấp | Tác động của nhà cung cấp bên ngoài |
| Test qua API | Xác thực, quyền, ánh xạ command và hợp đồng | Mọi interleaving hoặc mọi đường job |
| Test worker và tích hợp mô phỏng | Message trùng, timeout, dừng và xử lý lại | Mọi hành vi ngoài hợp đồng mô phỏng |
| Kiểm tra đối soát | Quan hệ giữa sổ và tác động đã có | Ngăn mọi tác động sai ngay lúc xảy ra |

Không cần đẩy mọi kiểm thử lên tầng cao nhất. Chọn tầng thấp nhất có thể chứng minh thuộc tính, rồi bổ sung những tầng cần thiết cho các giả định xuyên ranh giới.

## 6. Bắt đầu bằng các ca nhỏ có kết quả xác định

Với K = 10, có thể viết các ca sau trước khi sinh chuỗi phức tạp.

| Ca | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Giữ hợp lệ | Giữ 3 khi A = 10 | Một hold ACTIVE lượng 3; A = 7, H = 3 |
| Vượt khả dụng | Giữ 11 khi A = 10 | Không tạo quyền giữ |
| Miền giá trị | Giữ 0 hoặc số âm | Bị từ chối theo hợp đồng |
| Xác nhận | Xác nhận hold ACTIVE lượng 3 | H giảm 3, S tăng 3, A không đổi |
| Giải phóng | Giải phóng hold ACTIVE lượng 3 | H giảm 3, A tăng 3 |
| Sai trạng thái | Xác nhận hold đã RELEASED | Không tạo bán hoặc tác động ngoài trái phép |
| Retry | Gửi lại cùng ý định giữ | Cùng kết quả nghiệp vụ, không thêm lượng giữ |
| Sai chủ thể | Actor khác thao tác hold không thuộc quyền | Không thay đổi hold hoặc cấp dữ liệu ngoài quyền |
| Ranh giới | Giữ đúng 10 rồi giữ thêm 1 | Lần đầu có thể thành công; lần sau không được cấp thêm |

Các ca này giúp kiểm tra hợp đồng và oracle. Nếu test cơ sở chưa xác định được trạng thái kỳ vọng, một bộ sinh ngẫu nhiên lớn thường chỉ tạo lỗi khó giải thích hơn.

### 6.1. Kiểm tra tính hữu ích bên cạnh tính an toàn

Không chỉ assert “H + S <= K”. Cần chứng minh một yêu cầu đủ điều kiện thật sự có thể thành công trong môi trường bình thường.

Ví dụ, hệ thống trả lỗi cho mọi yêu cầu vẫn giữ tổng không vượt 10. Nó không đáp ứng postcondition và khả năng phục vụ mong đợi.

Tương tự, một cơ chế chống trùng từ chối mọi retry có thể tránh tạo trùng nhưng vi phạm hợp đồng trả lại kết quả đã chấp nhận. Cần kiểm tra cả định danh kết quả và tác động.

## 7. Minh họa Java: oracle đọc từ snapshot đã commit

Đoạn mã sau minh họa một oracle cho mô hình đóng của bài. Nó dùng thư viện chuẩn Java và không hiện thực dịch vụ giữ chỗ. Test harness phải cung cấp snapshot nhất quán, gồm đúng các hold của một phạm vi tồn kho.

~~~java
import java.math.BigInteger;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

final class InventoryInvariant {
    enum HoldState {
        ACTIVE, CONFIRMED, RELEASED
    }

    record Hold(String id, long quantity, HoldState state) {}

    record Snapshot(
            long capacity,
            long available,
            long held,
            long sold,
            List<Hold> holds) {}

    static void assertConsistent(Snapshot snapshot) {
        var capacity = BigInteger.valueOf(snapshot.capacity());
        var available = BigInteger.valueOf(snapshot.available());
        var held = BigInteger.valueOf(snapshot.held());
        var sold = BigInteger.valueOf(snapshot.sold());

        require(capacity.signum() >= 0, "Negative capacity");
        require(available.signum() >= 0, "Negative available");
        require(held.signum() >= 0, "Negative held");
        require(sold.signum() >= 0, "Negative sold");

        require(
                available.add(held).add(sold).equals(capacity),
                "Capacity conservation failed");

        var activeTotal = BigInteger.ZERO;
        var confirmedTotal = BigInteger.ZERO;
        Set<String> seenIds = new HashSet<>();

        for (var hold : snapshot.holds()) {
            require(hold.id() != null, "Missing hold id");
            require(seenIds.add(hold.id()), "Duplicate hold id in snapshot");
            require(hold.quantity() > 0, "Non-positive hold quantity");

            var quantity = BigInteger.valueOf(hold.quantity());
            switch (hold.state()) {
                case ACTIVE -> activeTotal = activeTotal.add(quantity);
                case CONFIRMED -> confirmedTotal = confirmedTotal.add(quantity);
                case RELEASED -> { }
            }
        }

        require(activeTotal.equals(held), "Held counter differs from holds");
        require(confirmedTotal.equals(sold), "Sold counter differs from holds");
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

Các lựa chọn có chủ đích:

- Dùng `BigInteger` để phép tổng của oracle không tràn cùng kiểu số production.
- Tính lại H và S từ các hold thay vì tin hoàn toàn vào bộ đếm.
- Kiểm tra tổng bảo toàn và từng đại lượng không âm.
- Kiểm tra ID lặp trong snapshot để tránh một phép join hoặc bộ đọc test vô tình đếm cùng hold nhiều lần.
- Không gọi hàm cập nhật tồn của production để tính kết quả mong đợi.

Oracle này vẫn có giới hạn:

- Nó chưa kiểm tra actor có quyền trên hold.
- Nó chưa phát hiện một tác động bên ngoài đã bị gửi hai lần nếu dữ liệu hiện tại vẫn khớp.
- Nó giả định mọi đơn vị đã bán trong mô hình đều được biểu diễn bởi hold CONFIRMED.
- Nó không áp dụng nguyên trạng cho nhập hàng, trả lại, điều chỉnh hoặc xác nhận một phần.
- Nó phụ thuộc test harness đọc đủ và đúng phạm vi, không lọc mất dữ liệu cần thiết.

Vì vậy, cần kết hợp với assertion về chuyển trạng thái, mô hình kỳ vọng và các đầu nhận tác động.

## 8. Kiểm thử dựa trên thuộc tính và mô hình

**Kiểm thử dựa trên thuộc tính** sinh nhiều đầu vào hoặc chuỗi thao tác để kiểm tra một thuộc tính tổng quát. **Kiểm thử dựa trên mô hình** dùng một mô hình tham chiếu để dự đoán hành vi hợp lệ.

Với tồn kho, mô hình có thể chỉ cần:

~~~text
khả năng cấp cố định
tập hold cùng lượng, chủ sở hữu và trạng thái
quan hệ actor và phạm vi
kết quả đã biết của từng ý định
~~~

Mô hình không cần sao chép cấu trúc bảng, SQL hoặc thuật toán khóa của production. Nó có thể tính khả dụng bằng cách lấy K trừ tổng ACTIVE và CONFIRMED trong bộ nhớ.

### 8.1. Sinh thao tác để đến được trạng thái sâu

Một bộ sinh chỉ chọn ID ngẫu nhiên thường tạo toàn lỗi không tìm thấy. Nó ít khi đến được các tình huống như giải phóng sau xác nhận hoặc retry sau mất phản hồi.

Nên có chủ đích sinh cả:

- Thao tác hợp lệ để xây dựng trạng thái.
- Giá trị biên: 0, 1, đúng khả dụng, hơn khả dụng và gần giới hạn kiểu số.
- Thao tác trên hold đang ACTIVE, đã CONFIRMED và đã RELEASED.
- Request lặp cùng khóa và request mới cùng tham chiếu nghiệp vụ.
- Actor cùng chủ thể, khác chủ thể và khác tenant.
- Thời gian trước hạn, đúng mốc theo hợp đồng và sau hạn.
- Chuỗi làm thay đổi một dữ kiện giữa kiểm tra và thực thi.

Không cần ấn định một tỷ lệ sinh đầu vào cho mọi hệ thống. Cần quan sát bộ sinh có thật sự chạm các trạng thái và tổ hợp quan trọng không.

### 8.2. So kết quả từng bước với mô hình

Một vòng kiểm thử khái quát:

~~~text
1. Tạo fixture mới và mô hình ban đầu tương ứng.
2. Sinh command cùng ngữ cảnh actor.
3. Tính kết quả được phép theo mô hình.
4. Gọi hệ thống.
5. Phân loại kết quả chắc chắn hoặc chưa rõ.
6. Đối chiếu hợp đồng và cập nhật mô hình khi đã biết tác động.
7. Đọc trạng thái tại mốc quan sát phù hợp.
8. So với mô hình và kiểm tra invariant.
9. Lặp cho command tiếp theo.
~~~

Không coi timeout là từ chối. Request có thể đã commit. Với kết quả chưa rõ, cần dùng khóa hoặc định danh ổn định để truy vấn, chờ xử lý có kiểm soát hoặc giữ các khả năng trong lịch sử kiểm tra cho đến khi phân giải được.

Nếu mô hình luôn cập nhật theo response thành công mà không so với trạng thái thật, nó có thể bỏ sót trường hợp API báo thành công nhưng không tạo hold. Nếu mô hình coi mọi lỗi là không có tác động, nó có thể báo sai sau một lần mất phản hồi.

### 8.3. Lưu seed và rút gọn chuỗi gây lỗi

Khi thất bại, cần biết seed, chuỗi command, actor, thời gian logic và các lỗi được chèn. Chỉ thông báo “random test failed” không đủ để điều tra.

Có thể rút gọn chuỗi để tìm ít bước nhất còn gây lỗi. Nhưng phải giữ quan hệ cần thiết: không xóa bước tạo hold rồi biến lỗi cạnh tranh thành lỗi không tìm thấy.

Nên dùng tham chiếu tượng trưng trong lịch sử, như hold được tạo ở bước trước, thay vì phụ thuộc ID được cấp ngẫu nhiên. Điều đó giúp tái hiện và rút gọn ổn định hơn.

## 9. Kiểm thử đồng thời có chủ đích

Tình huống cơ sở: tồn có K = 10, hai request khác ý định cùng giữ 7.

Trong điều kiện không có lỗi hạ tầng, không có thao tác khác và thời gian hết hạn được kiểm soát:

~~~text
Chỉ một request được cấp 7.
Request còn lại không được cấp thêm 7.
Trạng thái sau cùng: A=3, H=7, S=0.
~~~

Đây vừa kiểm tra không cấp quá, vừa kiểm tra hệ thống không từ chối vô cớ cả hai.

### 9.1. Mã khung Java cho hai request cạnh tranh

Đoạn sau dùng test harness giả định. `fixture.client(0)` và `fixture.client(1)` phải đi qua các request hoặc session dữ liệu độc lập; các kiểu fixture và response chưa được hiện thực trong đoạn mã.

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

void doesNotOverReserveUnderContention() throws Exception {
    var fixture = freshInventoryFixture(10);
    var ready = new CountDownLatch(2);
    var start = new CountDownLatch(1);
    var pool = Executors.newFixedThreadPool(2);

    try {
        var first = pool.submit(() -> {
            ready.countDown();
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Start gate timed out");
            }
            return fixture.client(0).reserve(7, "intent-1");
        });

        var second = pool.submit(() -> {
            ready.countDown();
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Start gate timed out");
            }
            return fixture.client(1).reserve(7, "intent-2");
        });

        if (!ready.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Workers did not become ready");
        }
        start.countDown();

        var firstResult = first.get(10, TimeUnit.SECONDS);
        var secondResult = second.get(10, TimeUnit.SECONDS);
        int accepted = (firstResult.accepted() ? 1 : 0)
                + (secondResult.accepted() ? 1 : 0);

        if (accepted != 1) {
            throw new AssertionError("Expected exactly one accepted reservation");
        }

        var snapshot = fixture.readConsistentSnapshot();
        InventoryInvariant.assertConsistent(snapshot);

        if (snapshot.available() != 3
                || snapshot.held() != 7
                || snapshot.sold() != 0) {
            throw new AssertionError("Unexpected state after contention");
        }
    } finally {
        start.countDown();
        pool.shutdownNow();
    }
}
~~~

Các timeout chỉ giới hạn thời gian của ví dụ kiểm thử; harness cần điều chỉnh theo môi trường và dọn dẹp request, transaction cùng tài nguyên đúng cách khi có lỗi.

### 9.2. Cùng bắt đầu chưa bảo đảm một interleaving cụ thể

Latch giúp hai request có cơ hội chạy chồng lên nhau. Nó không tự chứng minh cả hai đã đọc cùng dữ kiện cũ trước khi ghi.

Nếu cần tái hiện một race cụ thể, có thể dùng điểm điều phối trong harness hoặc chèn lỗi có kiểm soát tại mốc phù hợp. Cần ghi lại lịch sử để biết interleaving mong muốn đã xảy ra.

Không đặt một barrier yêu cầu cả hai luồng đi qua tại vị trí mà luồng thứ nhất đã giữ khóa ngăn luồng thứ hai tới barrier. Cách đó có thể tạo deadlock do chính test.

Chạy lặp với nhiều lịch thực thi giúp tăng cơ hội tìm lỗi, nhưng không thay thế việc hiểu cơ chế cạnh tranh. Một lần chạy qua không chứng minh mọi interleaving đều an toàn.

### 9.3. Xác nhận và giải phóng cùng một hold

Một ca quan trọng khác là hai luồng cùng chọn hold ACTIVE:

~~~text
Luồng 1: xác nhận bán.
Luồng 2: giải phóng hoặc xử lý hết hạn.
~~~

Chỉ một chuyển trạng thái cuối được thắng. Nếu CONFIRMED thắng, lượng phải đi vào S và không đồng thời được trả về A. Nếu RELEASED thắng, xác nhận không được tạo bán hoặc lệnh giao hàng trái phép.

Kiểm tra cả trạng thái cuối, các tổng và lệnh tác động. Tổng số lượng có thể vẫn khớp nếu hai sai sót bù nhau, nên không bỏ assertion theo từng ý nghĩa.

## 10. Thuộc tính an toàn và thuộc tính theo thời gian

Một số thuộc tính yêu cầu điều xấu không xảy ra. Một số yêu cầu công việc hợp lệ cuối cùng được tiến triển.

| Nhóm | Ví dụ | Điều kiện cần chỉ rõ |
| --- | --- | --- |
| An toàn | Không cấp quá K, không xác nhận hold đã giải phóng | Mốc commit và nguồn có thẩm quyền |
| Tiến triển | Hold hết hạn được xử lý, lệnh chờ được đối soát | Worker có hoạt động, hạ tầng khả dụng, giới hạn kiểm thử |
| Tác động có giới hạn số lần | Một quyết định chỉ tạo số lệnh được phép | Định danh nghiệp vụ và hợp đồng của bên nhận |
| Hội tụ | Projection cuối cùng khớp nguồn sau khi xử lý hết sự kiện | Điểm quan sát và điều kiện hoàn tất hàng đợi |

Không dùng “sẽ nhất quán sau” để cho phép cấp quá tồn ở nơi quyết định ngay. Cũng không yêu cầu một projection bất đồng bộ luôn khớp từng thời điểm nếu hợp đồng của nó chỉ yêu cầu hội tụ.

Một test chờ tối đa một khoảng thời gian chỉ cung cấp bằng chứng trong điều kiện đã chạy. Nó không chứng minh toán học rằng hệ thống luôn tiến triển trong mọi tương lai.

### 10.1. Kiểm tra lịch sử đồng thời khi cần một hành động nguyên tử

Với API giữ chỗ có hợp đồng nguyên tử, có thể lưu thời điểm bắt đầu, kết thúc, định danh ý định và kết quả. Sau đó kiểm tra liệu có một thứ tự các thao tác phù hợp với mô hình tuần tự hay không:

- Thao tác kết thúc trước khi thao tác khác bắt đầu phải đứng trước trong thứ tự phù hợp.
- Các thao tác chạy chồng nhau có thể được sắp theo thứ tự nào giữ đúng mô hình và kết quả.
- Thao tác chưa rõ kết quả không được tự coi như không tồn tại.
- Định danh và quyền của từng thao tác vẫn phải được kiểm tra.

Cách lập luận này thường được dùng khi kiểm tra tính tuyến tính hóa của một API. Một checker chỉ kiểm tra các lịch sử đã thu được và mô hình đã cung cấp; nó không chứng minh mọi lịch sử có thể có.

Không áp đặt cùng một điểm nguyên tử cho toàn bộ workflow nhiều dịch vụ nếu hợp đồng thực tế có trạng thái chờ và bù trừ. Cần kiểm tra các thuộc tính cục bộ, quy tắc chuyển trạng thái và điều kiện hội tụ đúng với kiến trúc.

## 11. Chèn lỗi, retry và tác động bên ngoài

Nhiều vi phạm không xuất hiện trong luồng thành công. Cần chủ động tạo những điểm dừng hoặc mất phản hồi đã được xác định.

| Điểm gây lỗi | Nguy cơ | Điều cần kiểm tra |
| --- | --- | --- |
| Trước khi transaction commit | Lưu một phần thay đổi | Không có hold hoặc bộ đếm dở dang đã commit |
| Sau commit, trước response | Client không biết đã thành công | Truy vấn hoặc retry cùng ý định tìm đúng kết quả |
| Sau commit, trước khi phát sự kiện | Mất tác vụ phía sau | Ý định còn trong outbox và được xử lý theo hợp đồng |
| Sau gửi ngoài, trước nhận phản hồi | Tác động đã xảy ra nhưng nội bộ chưa biết | Không tạo ý định mới hoặc giải phóng quyền lợi sai |
| Khi worker khởi động lại | Xử lý lại message | Không nhân tác động ngoài số lần cho phép |
| Khi nhận sự kiện trùng | Cập nhật bộ đếm hai lần | Trạng thái và số lượng chỉ đổi hợp lệ |
| Khi sự kiện đến lệch thứ tự | Quay lùi trạng thái | Sự kiện cũ không làm sống lại quyền đã kết thúc |
| Khi hết hạn chạy cùng xác nhận | Vừa bán vừa trả khả dụng | Chỉ một chuyển trạng thái cuối thắng |
| Khi hết hạn chỉ xóa bản ghi | Bộ đếm giữ không được cập nhật | Dữ liệu tổng và chi tiết vẫn khớp |

### 11.1. Timeout là trạng thái chưa rõ, không phải bằng chứng rollback

Trong test, có thể để máy chủ commit rồi chặn response. Nếu client retry bằng cùng ý định, hệ thống phải trả hoặc tìm lại kết quả theo hợp đồng mà không tạo thêm hold.

Khi thử với lệnh ngoài, nhà cung cấp mô phỏng cần có khả năng ghi nhận tác động rồi làm mất phản hồi. Nếu mock chỉ luôn ném lỗi trước mọi tác động, test sẽ bỏ sót khoảng nguy hiểm nhất.

Một fake provider có thể lưu định danh lệnh, số lần nhận và số tác động nghiệp vụ. Số lần gọi mạng có thể lớn hơn một trong khi số tác động phải nằm trong giới hạn cho phép.

Khả năng đó phải khớp hợp đồng cần kiểm tra. Nếu bên ngoài không hỗ trợ chống trùng hoặc truy vấn phù hợp, không thiết kế fake mạnh hơn thực tế rồi kết luận hệ thống an toàn.

### 11.2. Xác nhận tồn và thanh toán không nhất thiết là một transaction chung

Nếu có cả thanh toán và tồn kho ở các dịch vụ khác nhau, một lỗi có thể để hệ thống ở trạng thái trung gian hợp lệ như đang đối soát hoặc đang hoàn tác.

Cần xác định invariant nào phải đúng ngay, ví dụ không cấp vượt tồn, và thuộc tính nào được giải quyết bởi quy trình tiếp theo, ví dụ một khoản thu không hoàn tất đơn phải được đưa vào luồng xử lý phù hợp.

Không assert rằng mọi cột ở mọi dịch vụ phải đổi cùng một thời điểm nếu kiến trúc không cung cấp ranh giới đó. Ngược lại, không dùng bù trừ tương lai để bỏ qua việc hai khách đã được cam kết cùng một đơn vị hàng ngoài giới hạn sản phẩm.

### 11.3. Thời gian cần được kiểm soát

Các test hết hạn nên dùng đồng hồ có thể điều khiển và một cách kích hoạt job rõ ràng. Cần kiểm tra trước hạn, tại mốc có ý nghĩa theo hợp đồng và sau hạn.

Tránh dựa vào việc ngủ một khoảng ngắn rồi hy vọng scheduler đã chạy. Cũng không đổi đồng hồ giả nhưng quên một thành phần vẫn đọc giờ thật.

Khi expiry và xác nhận cạnh tranh, oracle phải dùng trạng thái có thẩm quyền và thứ tự được chấp nhận. Thời gian đến hạn không tự chứng minh transaction giải phóng đã hoàn tất.

## 12. Kiểm thử các invariant bảo mật khác cùng phương pháp

Ví dụ tồn kho giúp học cơ chế. Các tài sản khác cần oracle và trạng thái tương ứng.

| Invariant | Cách tạo tình huống | Bằng chứng cần xem |
| --- | --- | --- |
| Actor không tác động ngoài quyền | Trộn actor, tenant và ID có quan hệ khác nhau | Dữ liệu, trạng thái và response không mở quyền |
| Giá thực thi khớp quyết định | Sửa số lượng, địa chỉ hoặc dữ liệu báo giá sau xác nhận | Snapshot giá, số tiền thu và quyết định |
| Không tự duyệt khi bị cấm | Cùng danh tính dùng nhiều vai trò hoặc request | Danh tính thực, quan hệ người đề nghị–người duyệt |
| Phê duyệt chỉ bao phủ nội dung đã duyệt | Đổi số tiền, người nhận hoặc đối tượng | Binding, revision và lệnh thực thi |
| Hoàn không vượt quyền lợi | Chia nhỏ, dùng khóa mới và gửi đồng thời | Đã hoàn, đang giữ và phân bổ theo giao dịch |
| Retry không mở rộng quyền | Cùng khóa, khác khóa và nhiều worker | Ý định, quyết định, lệnh và tác động ngoài |
| Thu hồi có hiệu lực đúng phạm vi | Thu hồi giữa lúc xếp hàng và thực thi | Revision, ranh giới cấp phép và tác vụ đã ra ngoài |
| Quản trị không tự mở rộng thẩm quyền | Sửa chính sách rồi phát hành hoặc rollback | Phê duyệt nội dung, phiên bản và actor thực |

Không dùng cùng một oracle số học cho mọi loại thuộc tính. Quyền theo đối tượng cần dữ kiện quan hệ; phê duyệt cần nội dung và danh tính; tác động bên ngoài cần bằng chứng từ bên nhận.

Một phép tổng đúng không chứng minh người nhận đúng. Một unique constraint đúng không chứng minh số tiền đúng. Bộ kiểm thử phải giữ các thuộc tính độc lập cần thiết.

## 13. Làm cho kiểm thử đáng tin và có thể tái hiện

### 13.1. Fixture phải có giả định rõ

Mỗi test nên biết:

- Dữ liệu ban đầu và phạm vi cô lập.
- Tenant, actor, quan hệ và credential cần thiết.
- Các job nền nào được bật hoặc điều khiển.
- Đồng hồ và trạng thái queue.
- Cấu hình transaction và số instance liên quan.
- Những tương tác bên ngoài được mô phỏng như thế nào.

Hai test cùng dùng một SKU hoặc một khóa idempotency có thể làm nhau thất bại. Ngược lại, việc vô tình dùng một kết nối và transaction duy nhất cho hai luồng có thể làm test cạnh tranh bị tuần tự hóa.

Khi một request timeout, test teardown cần dừng hoặc chờ các tác vụ, rollback transaction còn mở và xử lý tài nguyên trước khi tái sử dụng fixture. Không xóa dữ liệu trong khi request vẫn có thể commit phía sau.

### 13.2. Phân biệt lỗi sản phẩm với lỗi quan sát

Một failure cần được phân loại bằng bằng chứng:

- Invariant thật sự bị phá.
- Oracle dùng sai mô hình hoặc sai phạm vi.
- Snapshot ghép nhiều thời điểm.
- Harness không đạt interleaving dự kiến.
- Fixture bị job khác hoặc test khác tác động.
- Hạ tầng kiểm thử không đáp ứng điều kiện của kịch bản.

Không tự gắn nhãn flaky rồi bỏ qua một lỗi cạnh tranh. Cũng không sửa production chỉ để khớp một assertion xây trên giả định sai.

### 13.3. Kiểm tra oracle có đủ nhạy không

Có thể đưa cho oracle các snapshot cố ý không hợp lệ, như tổng lệch, bộ đếm không khớp chi tiết hoặc ID lặp, để biết nó phát hiện đúng loại sai lệch dự kiến.

Với test trạng thái, có thể xác nhận một lỗi giả lập ở ranh giới phù hợp thật sự làm assertion thất bại. Mục tiêu là biết test có khả năng quan sát điều xấu, không phải tạo thêm kiểm thử lặp lại từng dòng triển khai.

Nếu oracle luôn qua cả với dữ kiện vi phạm rõ ràng, số lượng chuỗi ngẫu nhiên chạy được không tạo thêm giá trị.

## 14. Báo cáo bằng chứng và giới hạn

Một báo cáo kiểm thử invariant nên nói được:

~~~text
Thuộc tính:
  Điều cần giữ và phạm vi áp dụng.

Kịch bản:
  Actor, thao tác, dữ liệu ban đầu và lỗi được chèn.

Mốc quan sát:
  Snapshot nhất quán, sau commit, sau xử lý queue hoặc qua lịch sử.

Kết quả:
  Dữ kiện trạng thái, định danh, số lượng và tác động được kiểm tra.

Phạm vi môi trường:
  Cơ sở dữ liệu, số instance và hợp đồng bên ngoài được mô phỏng.

Giới hạn:
  Interleaving, đường ghi hoặc loại điều chỉnh chưa được kiểm tra.
~~~

Nếu tìm thấy counterexample, nên rút gọn thành chuỗi ngắn có thể tái hiện và bổ sung nó vào kiểm thử hồi quy phù hợp.

Sau khi sửa, chạy các kiểm thử chạm thuộc tính và những đường bị ảnh hưởng. Nếu có thay đổi mới, failure hoặc giả định chưa được giải quyết, mở rộng phạm vi tương ứng. Không cần lặp vô hạn cùng một bộ đã ổn định chỉ để tăng số lần chạy.

Kết quả qua cho thấy các trường hợp đã quan sát phù hợp với mô hình. Nó không chứng minh mọi đầu vào, mọi lịch thực thi hoặc mọi tác động ngoài hợp đồng đều an toàn. Cần kết hợp với thiết kế ràng buộc, kiểm tra đường ghi và vận hành đối soát.

## 15. Những sai lầm thường làm kiểm thử invariant mất giá trị

| Sai lầm | Điều bị bỏ sót | Cách điều chỉnh |
| --- | --- | --- |
| Chỉ xem HTTP 200 hoặc exception | Trạng thái thật và tác động đã commit | Đọc nguồn có thẩm quyền cùng đầu nhận tác động |
| Oracle gọi cùng logic production | Cùng sai ở cả hai phía | Dùng mô hình đơn giản hoặc nguồn đối chiếu độc lập |
| Chỉ kiểm tra một tổng | Sai người nhận, trạng thái hoặc sai số bù nhau | Kiểm tra quan hệ và ý nghĩa từng thành phần |
| Chạy tuần tự để kiểm tra race | Không có cạnh tranh thực sự | Dùng request độc lập và điều phối có chủ đích |
| Dùng sleep làm điều kiện đúng | Phụ thuộc scheduler và tải môi trường | Đồng hồ kiểm soát, latch và tín hiệu hoàn tất |
| Mọi lỗi đều coi là rollback | Bỏ sót commit rồi mất phản hồi | Phân loại kết quả chưa rõ và phân giải theo ý định |
| Snapshot đọc rời rạc | Tạo trạng thái giả do nhiều thời điểm | Snapshot nhất quán hoặc mốc dừng có kiểm soát |
| Random không có seed và lịch sử | Không tái hiện hoặc rút gọn được | Ghi seed, command, actor và lỗi được chèn |
| Mock để chứng minh khóa dữ liệu | Không có ngữ nghĩa transaction thật | Test tích hợp với lưu trữ đại diện |
| Cuối cùng khớp nên coi như đúng | Tác động sai trước đó có thể đã xảy ra | Kiểm tra lịch sử và các mốc invariant bắt buộc |
| Một lần chạy qua là đủ cho mọi lịch | Phạm vi bằng chứng quá hẹp | Kết hợp interleaving có chủ đích và kiểm tra cơ chế |
| Chấp nhận test từ chối mọi thứ | Chỉ an toàn nhưng không phục vụ đúng | Kiểm tra postcondition và tiến triển trong điều kiện đã nêu |

## 16. Bài tập tự kiểm tra

### Bài 1: tổng bằng 10 nhưng vẫn sai

Sau một lần giải phóng hold 3, hệ thống chuyển 3 từ H sang S thay vì A. Tổng A + H + S vẫn bằng K.

**Gợi ý trả lời:** invariant bảo toàn đơn lẻ không phát hiện đầy đủ lỗi. Cần postcondition của giải phóng, trạng thái RELEASED, tổng ACTIVE so với H và tổng CONFIRMED so với S. Không có xác nhận bán thì S không được tăng trong mô hình này.

### Bài 2: hai request đã đồng thời chưa?

Test gửi request thứ hai sau khi request thứ nhất trả về. Cả hai xử lý đúng và nhóm kết luận đã ngăn race.

**Gợi ý trả lời:** đây là kiểm thử tuần tự. Cần request hoặc session độc lập có cơ hội chồng thời gian, và khi cần phải điều phối một interleaving cụ thể. Kết quả chạy qua không tự chứng minh mọi lịch an toàn.

### Bài 3: timeout rồi trạng thái tăng

Một request giữ 2 bị timeout. Test lập tức assert không có hold mới, nhưng cơ sở dữ liệu có một hold ACTIVE lượng 2.

**Gợi ý trả lời:** timeout không chứng minh request chưa commit. Cần phân giải bằng cùng ý định hoặc khóa, kiểm tra đúng một kết quả và không tạo thêm khi retry. Assertion “không có tác động” chỉ đúng nếu hợp đồng và bằng chứng xác nhận từ chối chắc chắn.

### Bài 4: snapshot lệch trong lúc job chạy

Test đọc A, job xác nhận một hold, rồi test đọc H và S. Tổng thu được khác K.

**Gợi ý trả lời:** có thể đang ghép nhiều thời điểm. Trước khi kết luận sản phẩm sai, cần snapshot nhất quán hoặc mốc quan sát có kiểm soát. Sau đó mới đối chiếu trạng thái và lịch sử để xác định có vi phạm thật hay không.

## 17. Các điểm cần ghi nhớ

Kiểm thử invariant bắt đầu từ một thuộc tính chính xác, có phạm vi và mốc quan sát rõ. Bộ kiểm thử cần kiểm tra cả trạng thái, chuyển trạng thái, quyền và số lần tác động theo mô hình nghiệp vụ.

Oracle phải đủ độc lập để phát hiện lỗi, dữ kiện quan sát phải nhất quán và các tình huống cạnh tranh hoặc lỗi phải thật sự được tạo ra. Chuỗi sinh tự động, mô hình tham chiếu, kiểm thử tích hợp và đầu nhận mô phỏng bổ sung cho nhau.

Câu hỏi cốt lõi là: **Chuỗi thao tác nào có thể làm điều kiện bảo vệ nghiệp vụ sai, và bộ kiểm thử có quan sát được vi phạm đó ở đúng nơi, đúng thời điểm hay không?**
