# Race condition test — Kiểm thử lỗi cạnh tranh trong logic nghiệp vụ

## 1. Mục tiêu của bài học

Một hệ thống có thể chặn đúng yêu cầu sai khi chạy tuần tự nhưng vẫn vi phạm quy tắc nghiệp vụ khi hai yêu cầu được xử lý chồng lấn. Ví dụ hai lần giữ tiền đều đọc cùng hạn mức còn lại, hai lần đặt hàng đều thấy chưa có đơn hoặc một yêu cầu sửa nội dung chen vào giữa bước kiểm tra và sử dụng phê duyệt.

**Race condition test** là kiểm thử có chủ đích các lịch thực thi đồng thời để tìm kết quả trái với quy tắc nghiệp vụ. Trong security testing, điều cần chứng minh là người gọi không thể lợi dụng thời điểm hoặc sự lặp lại của thao tác để tạo hiệu lực ngoài quyền, vượt hạn mức hay bỏ qua bước bắt buộc.

Bài học thuộc module `SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`, kết nối kiểm thử cạnh tranh với business invariants, state machine, quyền theo đối tượng, transaction và idempotency. Các ví dụ phục vụ môi trường kiểm thử được kiểm soát, với dữ liệu và tích hợp được chuẩn bị để có thể quan sát, tái hiện và dọn dẹp.

Sau bài học, bạn có thể:

- Chọn tình huống cạnh tranh từ quy tắc cần bảo vệ, thay vì chỉ gửi thật nhiều request.
- Phân biệt các lỗi kiểm tra rồi hành động, mất cập nhật, write skew và sử dụng dữ liệu cũ.
- Điều khiển thời điểm bắt đầu hoặc các điểm xen kẽ mà không tự tạo deadlock.
- Kiểm chứng phản hồi, trạng thái đã commit và hiệu lực ngoài hệ thống.
- Biến lỗi đồng thời khó tái hiện thành ca hồi quy có bằng chứng rõ ràng.

## 2. Race condition trong bảo mật nghiệp vụ là gì?

Race condition xuất hiện khi tính đúng của một hành vi phụ thuộc vào thứ tự thực thi chưa được kiểm soát đầy đủ. Không phải mọi thứ tự khác nhau đều là lỗi: hai yêu cầu hợp lệ có thể được xử lý theo nhiều thứ tự, miễn các kết quả đã ghi nhận vẫn tuân thủ chính sách.

Xét hạn mức khả dụng `1000000 VND`, hai yêu cầu A và B đều cần giữ `700000 VND`:

```text
A: đọc khả dụng = 1000000
B: đọc khả dụng = 1000000
A: kiểm tra 700000 <= 1000000 -> đạt
B: kiểm tra 700000 <= 1000000 -> đạt
A: ghi một lần giữ 700000
B: ghi một lần giữ 700000
```

Từng lần kiểm tra riêng lẻ có vẻ đúng, nhưng tổng giữ là `1400000 VND`, vượt hạn mức. Người lạm dụng không cần gửi số tiền sai định dạng; họ chỉ cần làm các yêu cầu hợp lệ chồng lấn vào thời điểm có lợi.

Một race condition có thể xảy ra giữa các thread, các request, nhiều instance, worker bất đồng bộ hoặc giữa hệ thống nội bộ và dịch vụ ngoài. Sửa bằng một khóa chỉ tồn tại trong bộ nhớ của một instance không đương nhiên bảo vệ các instance khác.

## 3. Bắt đầu từ bất biến và kết quả được phép

### 3.1. Viết điều kiện có thể đo được

Một số bất biến điển hình:

- Tổng tiền giữ còn hiệu lực không vượt hạn mức được cấp.
- Mỗi hồ sơ chỉ tạo tối đa một đơn hàng trong phạm vi chính sách.
- Mỗi thao tác thu tiền đã định danh chỉ tạo tối đa một hiệu lực tương ứng.
- Không hoàn vượt số tiền còn được phép hoàn của giao dịch.
- Đơn hàng chỉ được tạo từ revision đáp ứng điều kiện phê duyệt.
- Mã ưu đãi giới hạn một lượt không được áp dụng thành công cho hai lượt ngoài chính sách.
- Chủ thể phải đáp ứng quyền theo đối tượng tại điểm quyết định mà chính sách quy định.

Các phát biểu cần có phạm vi. Hệ thống cho phép đặt hàng nhiều đợt không nên bị kiểm thử theo giả định “mỗi hồ sơ chỉ có một đơn” nếu đó không phải quy tắc thật.

### 3.2. Tách an toàn khỏi khả năng hoàn thành

Với ví dụ hạn mức, thuộc tính an toàn là không thể giữ thành công cả hai khoản `700000 VND`. Tuy nhiên, một hệ thống từ chối mọi request cũng thỏa điều kiện đó.

Trong môi trường không có lỗi được tiêm thêm, hai yêu cầu đều đúng quyền và dữ liệu, cơ chế xử lý cạnh tranh cuối cùng phải cho phép công việc hợp lệ tiến triển theo hợp đồng. Với fixture này, kỳ vọng có thể là một lần giữ thành công, một lần bị từ chối hoặc xử lý xung đột phù hợp, và phần khả dụng cuối cùng là `300000 VND`.

Nếu hợp đồng cho phép trả xung đột cần client thử lại, bài kiểm thử phải mô tả bước thử lại và định danh thao tác được giữ. Không biến lỗi kỹ thuật tạm thời hoặc kết quả chưa rõ thành một kết quả nghiệp vụ cuối cùng chỉ để dễ đếm.

## 4. Nhận diện các kiểu cạnh tranh cần kiểm thử

| Kiểu lỗi | Tình huống minh họa | Điều cần quan sát |
| --- | --- | --- |
| Kiểm tra rồi hành động | Hai request cùng thấy chưa có đơn rồi cùng tạo | Số đơn đã commit và định danh nghiệp vụ |
| Mất cập nhật | Hai request đọc cùng số dư rồi cùng ghi giá trị mới | Sổ giao dịch có khớp số dư không |
| Write skew | Hai transaction sửa hai bản ghi khác nhau nhưng cùng phá hạn mức tổng | Tổng hợp trên toàn phạm vi bất biến |
| Thay đổi giữa kiểm tra và sử dụng | Hồ sơ được sửa sau khi kiểm tra revision đã duyệt | Nội dung thực sự đặt hàng có được duyệt không |
| Tranh chấp chuyển trạng thái | Hủy và đặt hàng cùng hồ sơ | Lịch sử và trạng thái cuối có hợp lệ theo state machine không |
| Xử lý lặp phân tán | Hai worker cùng tiếp nhận một thao tác | Số hiệu lực logic trong và ngoài hệ thống |
| Worker cũ tiếp tục sau phục hồi | Lease hết hạn, worker mới tiếp quản, worker cũ hoạt động lại | Worker mất quyền sở hữu có tạo thêm hiệu lực không |

Không nên chỉ kiểm tra một ô dữ liệu cuối cùng. Trong lỗi mất cập nhật, số dư có thể vẫn không âm nhưng sổ giao dịch đã ghi hai khoản chi. Khi đó bất biến kinh tế đã bị phá dù một phép kiểm tra `balance >= 0` vẫn vượt qua.

## 5. Viết đặc tả cho một race condition test

Một kịch bản nên ghi rõ:

1. Quy tắc bị nhắm tới và mục tiêu của người lạm dụng.
2. Các chủ thể, phạm vi tổ chức và quyền cần thiết.
3. Dữ liệu ban đầu đã commit.
4. Hai hoặc nhiều hành động cạnh tranh.
5. Cửa sổ xen kẽ cần tạo hoặc quan sát.
6. Những kết quả cuối được phép và bị cấm.
7. Các hiệu lực phải kiểm chứng, cùng điểm kết thúc quan sát.
8. Cách giải phóng điểm chờ và xử lý khi test hết thời hạn.

Ví dụ đặc tả rút gọn:

```yaml
scenario: concurrent-reservations-cannot-exceed-budget
invariant: Tổng giữ tiền còn hiệu lực không vượt 1000000 VND
initialState:
  available: 1000000
  currency: VND
  activeReservations: 0
actions:
  - operation: reserve-A
    amount: 700000
  - operation: reserve-B
    amount: 700000
interleavingGoal: Hai yêu cầu cùng cạnh tranh trên một hạn mức
expectedFinalState:
  successfulReservations: 1
  reservedTotal: 700000
  available: 300000
forbidden:
  - Hai lần giữ tiền cùng thành công
  - Sổ giữ tiền không khớp hạn mức khả dụng
```

Đây là ví dụ mô tả trong bài học, không yêu cầu tạo thêm tệp. Tiền điều kiện còn bao gồm việc hai yêu cầu đúng quyền, không có giao dịch khác và không có lý do từ chối độc lập. Nếu thiếu các điều kiện này, test có thể vượt qua vì một request bị chặn trước khi tới vùng cạnh tranh.

## 6. Chuẩn bị môi trường để bằng chứng có ý nghĩa

### 6.1. Dùng nơi lưu dữ liệu đủ tương đồng

Kiểm thử ràng buộc duy nhất, khóa, mức cô lập hoặc xung đột cập nhật cần database có đặc tính liên quan phù hợp với triển khai cần bảo vệ. Mock repository có thể kiểm tra nhánh xử lý, nhưng không chứng minh hai transaction thật sẽ được phân xử đúng.

Ghi nhận cấu hình quan trọng của môi trường kiểm thử: loại database, mức cô lập được dùng, ràng buộc dữ liệu, số instance, cách chạy worker và cơ chế retry. Không cần giống toàn bộ production, nhưng những đặc tính quyết định kết quả cạnh tranh phải được đại diện đúng.

### 6.2. Tách transaction và ngữ cảnh của các request

Hai hành động phải thật sự có khả năng chạy đồng thời. Nếu chúng dùng chung một transaction bao ngoài hoặc cùng kết nối bị tuần tự hóa, test có thể không chạm tới lỗi cần tìm.

Commit dữ liệu khởi tạo trước khi gửi các request. Khi quan sát sau cùng, đọc lại bằng ngữ cảnh thích hợp để thấy dữ liệu đã commit, thay vì chỉ nhìn đối tượng còn trong cache của phiên làm việc cũ.

Với lời gọi service trực tiếp từ các thread kiểm thử, ngữ cảnh bảo mật gắn với thread có thể không tự truyền sang. Cần thiết lập rõ chủ thể cho từng hành động hoặc gọi qua API bằng client có danh tính riêng. Không để việc mất ngữ cảnh xác thực khiến cả hai request đều bị từ chối và tạo cảm giác cơ chế chống race đang hoạt động.

### 6.3. Kiểm soát các yếu tố gây nhiễu

Tạo dữ liệu riêng cho mỗi lần chạy; không dùng chung một ví hoặc một mã ưu đãi với test khác. Nếu có rate limit, chống tự động hóa hoặc lỗi tích hợp ngoài, cần nhận diện chúng để không nhầm với cơ chế bảo vệ bất biến.

Một request bị chặn bởi giới hạn tần suất có thể là hành vi hợp lệ của hệ thống, nhưng không chứng minh transaction giữ hạn mức an toàn. Bằng chứng cần chỉ ra cơ chế và quy tắc thực sự đã được kiểm tra.

## 7. Điều khiển thời điểm bắt đầu và điểm xen kẽ

### 7.1. Bắt đầu gần đồng thời

Một hàng rào đầu vào cho hai tác vụ sẵn sàng rồi cùng được giải phóng giúp tăng cơ hội cạnh tranh. Cách này phù hợp để kiểm tra tích hợp, nhưng không bảo đảm hai request sẽ đọc cùng dữ liệu trước khi ghi: hệ điều hành, server hoặc database vẫn có thể tuần tự hóa chúng.

Chạy nhiều vòng có dữ liệu tách biệt giúp khám phá thêm lịch thực thi. Tuy nhiên, số vòng lớn không thay thế bằng chứng rằng cửa sổ nhạy cảm đã được tiếp cận.

### 7.2. Điều khiển cửa sổ kiểm tra rồi hành động

Trong môi trường test, có thể thêm điểm điều khiển tại ranh giới quan trọng, chẳng hạn sau khi đọc dữ liệu nhưng trước khi thử cập nhật. Bộ test điều khiển request còn lại tiến tới một mốc cụ thể rồi giải phóng request đầu.

```text
Request A: đọc điều kiện -> báo đã tới điểm điều khiển -> tạm chờ
Request B: thực hiện bước cạnh tranh được chọn
Bộ test:  quan sát mốc cần thiết -> giải phóng A
Request A: tiếp tục cập nhật
Bộ test:  chờ kết quả, đọc dữ liệu đã commit và các hiệu lực
```

Điểm điều khiển phải có giới hạn thời gian, được giải phóng khi test lỗi và chỉ hoạt động trong môi trường kiểm thử. Nó không được thay đổi quyết định nghiệp vụ hoặc bỏ qua khóa để ép tạo lỗi.

### 7.3. Tránh deadlock do chính bộ test tạo ra

Nếu A đã giữ khóa mà B cần, không thể yêu cầu B đi qua khóa đó rồi mới cho A tiếp tục. Hàng rào như vậy có thể làm một triển khai đúng bị treo.

Khi cơ chế bảo vệ đúng khiến B phải chờ, bộ test nên nhận diện trạng thái chờ cần thiết hoặc dùng mốc trước khi B xin khóa, sau đó cho A hoàn tất. Mục tiêu là kiểm tra cơ chế phân xử thật, không buộc mọi request cùng đi qua một điểm mà triển khai đúng cố tình tuần tự hóa.

Không giữ điểm đồng bộ kiểm thử trong production hoặc mở quyền điều khiển nó cho người dùng. Điểm điều khiển nên được giới hạn trong cấu hình và bề mặt kiểm thử thích hợp.

## 8. Ví dụ bộ điều phối hai tác vụ bằng Java

Đoạn Java dưới đây minh họa cách cho hai tác vụ bắt đầu gần đồng thời và dùng chung một thời hạn. Mã sử dụng các kiểu chuẩn của Java; phần import được lược bỏ. Hai tác vụ cần trả kết quả khác `null`, còn thời hạn cần là một khoảng hợp lý cho test.

```java
static <T> List<T> startTogether(
        Callable<T> left,
        Callable<T> right,
        Duration timeout) throws Exception {

    if (timeout.isZero() || timeout.isNegative()) {
        throw new IllegalArgumentException("timeout must be positive");
    }

    long deadline = System.nanoTime() + timeout.toNanos();
    ExecutorService pool = Executors.newFixedThreadPool(2);
    CountDownLatch ready = new CountDownLatch(2);
    CountDownLatch start = new CountDownLatch(1);
    List<Future<T>> tasks = new ArrayList<>();

    try {
        for (Callable<T> action : List.of(left, right)) {
            tasks.add(pool.submit(() -> {
                ready.countDown();
                if (!start.await(remaining(deadline), TimeUnit.NANOSECONDS)) {
                    throw new TimeoutException("start gate timed out");
                }
                return action.call();
            }));
        }

        if (!ready.await(remaining(deadline), TimeUnit.NANOSECONDS)) {
            throw new TimeoutException("workers were not ready");
        }
        start.countDown();

        T a = tasks.get(0).get(remaining(deadline), TimeUnit.NANOSECONDS);
        T b = tasks.get(1).get(remaining(deadline), TimeUnit.NANOSECONDS);
        return List.of(a, b);
    } finally {
        start.countDown();
        for (Future<T> task : tasks) {
            task.cancel(true);
        }
        pool.shutdownNow();
    }
}

static long remaining(long deadline) throws TimeoutException {
    long nanos = deadline - System.nanoTime();
    if (nanos <= 0) {
        throw new TimeoutException("race test deadline exceeded");
    }
    return nanos;
}
```

Hàng rào trong ví dụ nằm trước lời gọi nghiệp vụ, nên không cố tình giữ khóa database trong lúc chờ request khác. Nó hỗ trợ tạo cạnh tranh ở đầu vào; để tái hiện một lịch xen kẽ cụ thể vẫn có thể cần các điểm điều khiển bổ sung.

`cancel(true)` và `shutdownNow()` chỉ yêu cầu ngắt tác vụ cục bộ. Chúng không bảo đảm request từ xa đã ngừng hoặc transaction trên server đã rollback. Client HTTP, câu lệnh database và điểm điều khiển cần có thời hạn riêng phù hợp; khi test thất bại, phải xác định các thao tác còn chạy trước khi kết luận trạng thái và dọn dữ liệu.

Không nuốt exception của tác vụ. Nếu một bên chết vì lỗi fixture hoặc mất quyền xác thực, kết quả còn lại không chứng minh được cơ chế phân xử hai yêu cầu nghiệp vụ hợp lệ.

## 9. Kịch bản vượt hạn mức: kiểm tra nhiều lớp bằng chứng

Với fixture `1000000 VND` và hai lần giữ `700000 VND`, cấu trúc kiểm thử có thể viết bằng giả mã:

```text
given:
  hạn mức đã commit, khả dụng 1000000 VND
  hai yêu cầu khác nhau, mỗi yêu cầu giữ 700000 VND
  cả hai có quyền và dữ liệu hợp lệ

when:
  gửi hai yêu cầu qua bộ điều phối bắt đầu đồng thời
  xử lý xung đột hoặc tra cứu kết quả theo hợp đồng
  chờ các thao tác liên quan kết thúc trong thời hạn

then:
  đúng một lần giữ được chấp nhận cuối cùng
  tổng giữ còn hiệu lực = 700000 VND
  khả dụng = 300000 VND
  tổng giữ + khả dụng = 1000000 VND
  không có hiệu lực phụ cho lần giữ bị từ chối
```

Oracle nên lấy số tiền từ dữ liệu fixture và chính sách, không gọi lại chính hàm production đang bị nghi có lỗi để tính kỳ vọng.

### 9.1. Một kết quả đánh lừa test yếu

Giả sử cả A và B đều đọc `1000000`, cùng ghi khả dụng thành `300000`, đồng thời mỗi bên tạo một dòng giữ `700000`. Khi đó:

```text
khả dụng cuối = 300000 VND
sổ giữ có 2 dòng, tổng = 1400000 VND
khả dụng + tổng giữ = 1700000 VND
```

Test chỉ kiểm tra khả dụng không âm sẽ vượt qua. Test kiểm tra cả sổ và quan hệ bảo toàn sẽ phát hiện dữ liệu không nhất quán.

### 9.2. Write skew khi có nhiều đối tượng

Nếu hạn mức dùng chung cho nhiều hồ sơ, chỉ khóa từng hồ sơ riêng có thể không bảo vệ được tổng hạn mức. Hãy dùng hai hồ sơ khác nhau cùng tiêu thụ một phạm vi hạn mức. Hai transaction không sửa cùng một hàng hồ sơ nhưng vẫn có thể cùng phá quy tắc tổng hợp.

Test này giúp phân biệt việc bảo vệ một bản ghi với việc bảo vệ đúng phạm vi bất biến. Cách triển khai có thể dùng cập nhật có điều kiện trên hạn mức, khóa thích hợp hoặc cơ chế cô lập tương ứng; kiểm thử cần chứng minh kết quả, không chỉ chứng minh một lệnh khóa đã được gọi.

## 10. Kịch bản cạnh tranh với phê duyệt và state machine

### 10.1. Sửa nội dung trong lúc đặt hàng

Tiền điều kiện: revision 7 đã được duyệt, và đổi số lượng là thay đổi bắt buộc duyệt lại. Hai hành động cạnh tranh:

- A đặt hàng dựa trên revision 7.
- B sửa số lượng, tạo revision 8.

Kết quả được phép phụ thuộc mô hình nghiệp vụ. Ví dụ hệ thống có thể tạo đơn từ snapshot revision 7 đã được duyệt, đồng thời coi revision 8 là thay đổi mới chưa có hiệu lực cho đơn đó. Hoặc hệ thống có thể từ chối đặt hàng khi phát hiện revision đã đổi.

Điều bị cấm là tạo đơn với nội dung revision 8 nhưng sử dụng phê duyệt chỉ dành cho revision 7. Vì vậy phải kiểm tra nội dung thực sự của đơn, revision tham chiếu và phê duyệt liên quan, không chỉ trạng thái `APPROVED` trên hồ sơ.

### 10.2. Hủy và đặt hàng cùng lúc

Xác định trước các chuyển trạng thái hợp lệ. Nếu đặt hàng trước rồi hủy vẫn là một chuỗi được phép, cả hai request thành công không tự chứng minh có lỗi. Nếu chính sách không cho hủy sau khi đã đặt, kết quả phải phản ánh điều đó.

Một cách đánh giá là xem kết quả có tương thích với một thứ tự xử lý hợp lệ theo hợp đồng hay không. Với các request chồng lấn, không tự áp một thứ tự cố định nếu hệ thống không cam kết thứ tự đó.

### 10.3. Thu hồi quyền hoặc đổi chủ sở hữu

Cho một request bắt đầu với quyền hợp lệ, sau đó thay đổi quyền hoặc phạm vi đối tượng ở thời điểm có kiểm soát. Cần nêu rõ chính sách hiệu lực quyền: kiểm tra tại lúc tiếp nhận, lúc commit hay một điểm quyết định khác, cùng độ trễ thu hồi được phép nếu có.

Không mặc định mọi quyền thu hồi ở hệ thống ngoài đều có hiệu lực tức thời trong transaction đang chạy. Test phải đối chiếu với cam kết thật, đồng thời tìm các đường dùng dữ liệu quyền cũ lâu hơn mức được phép hoặc bỏ qua kiểm tra đối tượng sau khi đối tượng đã đổi phạm vi.

## 11. Kịch bản cạnh tranh với idempotency và dịch vụ ngoài

### 11.1. Cùng khóa và cùng nội dung

Gửi hai yêu cầu cùng danh tính thao tác đồng thời. Nếu triển khai chỉ làm “tra cứu không thấy rồi tạo”, cả hai có thể cùng tiến vào xử lý.

Kỳ vọng cần gồm: khóa được ràng buộc với một thao tác logic, nội dung không bị thay thế, và tối đa một hiệu lực nghiệp vụ tương ứng. Một request có thể nhận đang xử lý hoặc phải tra cứu sau, tùy hợp đồng; không cần ép cả hai phản hồi giống từng byte.

### 11.2. Khác khóa nhưng cùng hiệu lực bị giới hạn

Thử hai khóa khác nhau trên cùng kỳ thu hoặc cùng hồ sơ chỉ được tạo một đơn. Nếu chỉ kiểm tra cùng khóa, bộ test có thể bỏ sót cách lạm dụng đơn giản là đổi khóa để tạo giao dịch thứ hai.

Đây là bảo vệ bất biến theo đối tượng, bổ sung cho idempotency. Với nghiệp vụ cho phép nhiều thao tác độc lập có cùng nội dung, cần đối chứng rằng hệ thống không khử trùng quá rộng và làm mất thao tác hợp lệ.

### 11.3. Cạnh tranh giữa worker và lần phục hồi

Tạo tình huống worker A chậm, lease xử lý hết hạn, worker B tiếp quản, sau đó A tiếp tục. Kiểm tra cơ chế sở hữu hiện tại có ngăn A tạo hiệu lực trái phép hay không.

Lease hết hạn không đồng nghĩa tiến trình cũ đã chết. Việc ngăn hiệu lực của worker cũ có thể cần cập nhật có điều kiện, thế hệ xử lý hoặc cơ chế tại nơi tạo hiệu lực, tùy thiết kế.

### 11.4. Không đếm nhầm số lần gọi và số hiệu lực

Một dịch vụ thanh toán có cơ chế khử trùng có thể được gọi nhiều lần nhưng chỉ tạo một khoản thu. Ngược lại, một bản ghi nội bộ duy nhất vẫn có thể đi cùng hai khoản thu ngoài hệ thống nếu ranh giới tích hợp bị lỗi.

Dùng bộ giả lập ngoài có thể ghi nhận định danh thao tác, lịch gọi, kết quả và số hiệu lực được chấp nhận. Không suy ra bảo đảm chống thu trùng chỉ từ transaction nội bộ hoặc số dòng trong bảng idempotency.

## 12. Tiêm lỗi và quan sát kết quả cuối

Race condition thường lộ rõ hơn khi kết hợp cạnh tranh với lỗi ở ranh giới quan trọng:

| Điểm lỗi | Biến thể cạnh tranh | Kỳ vọng cần kiểm chứng |
| --- | --- | --- |
| Sau kiểm tra, trước cập nhật | Request khác thay đổi cùng điều kiện | Không dùng điều kiện cũ để tạo hiệu lực trái chính sách |
| Sau một phần ghi, trước commit | Request khác chờ hoặc thử lại | Phần chưa commit không để lại dữ liệu nghiệp vụ dở dang |
| Sau commit, trước phản hồi | Client phát lại vì timeout | Nhận diện hiệu lực cũ, không tạo thêm |
| Sau hiệu lực ngoài, trước lưu kết quả | Worker khác tiếp quản | Đối soát hoặc tiếp tục cùng định danh ngoài theo hợp đồng |
| Trong lúc giao lại thông điệp | Hai consumer xử lý cùng sự kiện | Không cộng lặp hiệu lực nghiệp vụ |

Timeout phía client là bằng chứng chưa nhận được kết quả, không phải bằng chứng server đã thất bại. Sau timeout, kiểm tra trạng thái thao tác theo hợp đồng và tiếp tục quan sát thay vì lập tức gửi một giao dịch mới với định danh khác.

Với transaction thuần database, đọc trạng thái sau commit hoặc rollback. Với dịch vụ ngoài, rollback cục bộ không tự hoàn tác hiệu lực ngoài; test cần theo dõi trạng thái chưa xác định, đối soát hoặc bù trừ mà thiết kế cung cấp.

Với xử lý bất đồng bộ, xác định điểm kết thúc quan sát: các thao tác đã ở trạng thái cuối và thông điệp liên quan đã được xử lý trong môi trường kiểm thử. Chờ theo điều kiện có thời hạn. Một lần kiểm tra “chưa thấy giao dịch trùng” ngay sau phản hồi không đủ nếu worker vẫn có thể tạo nó sau đó.

## 13. Thu thập bằng chứng và đánh giá mức chắc chắn

### 13.1. Bằng chứng nên có

- Mã kịch bản và dữ liệu đầu vào đã được bảo vệ phù hợp.
- Chủ thể kiểm thử, phạm vi quyền và đối tượng bị tác động.
- Định danh request, thao tác, transaction hoặc sự kiện nếu hệ thống cung cấp.
- Các mốc gọi, trả kết quả và đi qua điểm điều khiển.
- Kết quả từng hành động và trạng thái cuối cùng đã commit.
- Các dòng sổ, sự kiện logic và hiệu lực ngoài liên quan.
- Lỗi database, timeout, retry và những thao tác còn chưa xác định kết quả.

Không ghi token, mật khẩu hoặc toàn bộ dữ liệu nhạy cảm vào báo cáo. Log quá nhiều ở vùng cạnh tranh cũng có thể thay đổi lịch thực thi; chọn các mốc đủ chẩn đoán mà không vô tình tuần tự hóa thao tác.

### 13.2. Kiểm tra lịch sử, không chỉ tổng số thành công

Hai phản hồi thành công có thể hợp lệ với hai chuyển trạng thái nối tiếp được phép. Một phản hồi lỗi cũng có thể che hiệu lực đã commit. Do đó cần gắn phản hồi với định danh thao tác và dữ liệu nghiệp vụ thực tế.

Với lịch sử có thể quy về xử lý tuần tự theo đặc tả, tìm một thứ tự phù hợp các ràng buộc của hợp đồng. Hành động đã kết thúc trước khi hành động khác bắt đầu có quan hệ thời gian rõ hơn hai hành động chồng lấn. Không chỉ sắp theo thời điểm client nhận phản hồi rồi coi đó là thứ tự commit.

### 13.3. Một lần không lỗi không phải chứng minh tuyệt đối

Test đầu vào đồng thời có thể không chạm được lịch xấu trong lần chạy hiện tại. Ghi nhận số vòng, lịch hoặc seed đã dùng và cửa sổ thực thi đã kiểm soát. Khi cần độ tin cậy cao hơn, tăng chất lượng điều khiển và oracle trước khi chỉ tăng số request.

Test có tái hiện xác định một lịch nguy hiểm cho bằng chứng mạnh về lịch đó, nhưng vẫn không bao phủ mọi lịch và mọi triển khai. Kết hợp kiểm thử với ràng buộc dữ liệu, thiết kế transaction và xem xét bất biến giúp đánh giá đầy đủ hơn.

## 14. Những cách kiểm thử dễ tạo kết luận sai

| Cách làm | Vì sao kết luận yếu | Cách cải thiện |
| --- | --- | --- |
| Chỉ gửi tuần tự | Không tạo vùng chồng lấn | Dùng tác vụ độc lập và điều khiển thời điểm phù hợp |
| Dùng `sleep` như bằng chứng đồng bộ | Không biết request đã tới đâu | Chờ mốc có ý nghĩa với thời hạn |
| Chỉ nhìn mã HTTP | Bỏ sót hiệu lực đã commit hoặc còn xử lý | Đọc trạng thái, sổ và tích hợp liên quan |
| Cùng transaction bao ngoài | Có thể che hành vi commit và khóa thật | Tách ranh giới request, commit fixture trước |
| Chỉ kiểm tra số dư không âm | Có thể bỏ sót mất cập nhật hoặc sổ cộng lặp | Kiểm tra tổng hợp và quan hệ bảo toàn |
| Tất cả request bị chặn từ đầu | Chưa kiểm tra cơ chế phân xử nghiệp vụ | Có đối chứng hợp lệ và xác nhận đi tới vùng cần kiểm tra |
| Hàng rào nằm sau khóa dùng chung | Tự tạo deadlock trong test | Chọn mốc trước khóa hoặc điều phối theo hành vi chờ đúng |
| Nuốt exception hoặc bỏ qua timeout | Biến kết quả chưa rõ thành thành công | Thất bại có bằng chứng và truy vết thao tác còn chạy |
| Chỉ đếm lời gọi dịch vụ ngoài | Không phân biệt retry với hiệu lực trùng | Quan sát định danh và hiệu lực được chấp nhận |
| Khóa trong một instance rồi chỉ test một instance | Không đại diện các tác nhân phân tán | Bổ sung nhiều instance hoặc worker nếu thuộc mô hình triển khai |

Một test không ổn định cần được sửa bằng cách làm rõ dữ liệu, thời hạn và lịch thực thi. Chạy lại đến khi xanh hoặc bỏ qua toàn bộ nhóm đồng thời có thể che đúng rủi ro mà nhóm đó được tạo ra để phát hiện.

## 15. Tổ chức chạy và chuyển lỗi thành hồi quy

Đặt các quy tắc trạng thái, phê duyệt và tính tiền ở lớp test nhanh phù hợp. Đặt ràng buộc database, transaction và cạnh tranh ở integration test có thể quan sát chúng. Chọn một số luồng xuyên hệ thống cho retry, nhiều instance và hiệu lực ngoài quan trọng.

Với mỗi lỗi race đã phát hiện:

1. Thu nhỏ còn số hành động tối thiểu gây vi phạm, thường bắt đầu từ hai hành động.
2. Giữ đúng điều kiện cùng chia sẻ tài nguyên, cùng khóa hoặc cùng phạm vi bất biến.
3. Tái hiện lịch xen kẽ bằng điểm điều khiển phù hợp nếu có thể.
4. Ghi kỳ vọng từ chính sách và dữ liệu fixture độc lập với đoạn mã lỗi.
5. Sửa cơ chế bảo vệ, rồi chạy lại ca tái hiện và các đối chứng liên quan.
6. Giữ ca hồi quy trong nhóm chạy phù hợp; bổ sung lịch hoặc seed mở rộng khi có ích.

Không sửa test để chấp nhận kết quả hiện tại chỉ vì hệ thống “đôi khi như vậy”. Nếu chính sách thực sự thay đổi, cập nhật bất biến, bảng trạng thái và các kỳ vọng liên quan cùng nhau.

Khi dọn dẹp sau lỗi, không chỉ xóa fixture trong lúc request từ xa còn chạy. Trước hết xác định hoặc cô lập các thao tác còn hoạt động theo thiết kế môi trường, sau đó dọn theo định danh của lần test. Điều này tránh dữ liệu xuất hiện lại hoặc test kế tiếp bị ảnh hưởng bởi worker của lần trước.

## 16. Danh sách kiểm tra cho race condition test

- Đã viết rõ bất biến và hậu quả nghiệp vụ nếu bị vi phạm.
- Đã xác định các hành động và tài nguyên chung tạo ra cạnh tranh.
- Đã có dữ liệu cùng quyền hợp lệ cho từng hành động khi chạy riêng.
- Đã commit fixture và tách ngữ cảnh transaction cần thiết.
- Đã chọn cách tạo chồng lấn, với thời hạn và đường giải phóng điểm chờ.
- Đã tránh hàng rào gây deadlock do chính bộ test tạo ra.
- Đã định nghĩa các kết quả được phép theo state machine và hợp đồng API.
- Đã kiểm tra số hiệu lực, tổng giá trị và trạng thái đã commit.
- Đã quan sát dịch vụ ngoài hoặc xử lý bất đồng bộ nếu chúng tham gia hiệu lực.
- Đã phân biệt timeout, xung đột, từ chối nghiệp vụ và thành công cuối cùng.
- Đã lưu mốc thực thi và dữ liệu tái hiện mà không làm lộ bí mật.
- Đã có kế hoạch xử lý thao tác còn chạy và dọn dữ liệu sau khi test lỗi.

Một race condition test có giá trị khi nó tạo được lịch cạnh tranh có ý nghĩa và chứng minh các hiệu lực cuối cùng vẫn tuân thủ quy tắc nghiệp vụ. Số request chỉ là cách tạo tình huống; bằng chứng quyết định nằm ở trạng thái đã commit, lịch sử hợp lệ và các hiệu lực thực tế trong toàn bộ phạm vi cần bảo vệ.
