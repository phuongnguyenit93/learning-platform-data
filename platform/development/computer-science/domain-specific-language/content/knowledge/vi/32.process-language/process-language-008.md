# Nhánh song song trong DSL quy trình

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích nhánh song song (parallel branch) trong DSL quy trình và phân biệt nó với nhánh điều kiện tuần tự.
- Mô tả cách một workflow tạo nhiều nhánh từ một điểm fork và đồng bộ tại điểm join.
- Phân biệt AND-split, AND-join, XOR, OR và các chính sách join như all, any, quorum.
- Thiết kế dữ liệu đầu vào, biến cục bộ, kết quả và trạng thái dùng chung giữa các nhánh.
- Kiểm soát race condition, ghi đè dữ liệu, thứ tự hoàn thành và giới hạn concurrency.
- Xử lý lỗi, timeout, retry, cancellation và compensation khi một nhánh thất bại.
- Xây dựng nhánh song song lồng nhau và tránh deadlock hoặc cạn kiệt worker.
- Lưu checkpoint, khôi phục và tiếp tục workflow có nhiều nhánh đang chạy.
- Theo dõi, giải thích và kiểm thử hành vi song song trong môi trường bất đồng bộ hoặc phân tán.

## 1. Nhánh song song là gì?

Nhánh song song (parallel branch) là một luồng thực thi được tạo ra khi một quy trình chia công việc thành nhiều phần có thể tiến hành độc lập. Các nhánh bắt đầu từ cùng một điểm trong workflow, có thể chạy đồng thời và thường gặp nhau tại một điểm đồng bộ trước khi quy trình tiếp tục.

Ví dụ, khi xử lý một đơn hàng, hệ thống có thể đồng thời:

- Kiểm tra tồn kho.
- Xác thực thanh toán.
- Kiểm tra rủi ro gian lận.
- Tính phí vận chuyển.

Các công việc này có thể được thực hiện độc lập vì chúng đọc dữ liệu khác nhau hoặc gọi các dịch vụ riêng. Khi kết quả cần thiết đã sẵn sàng, workflow mới quyết định có tiếp tục tạo đơn hay phải từ chối.

Một DSL quy trình có thể biểu diễn:

~~~text
workflow "process_order" {
    parallel {
        branch "inventory":
            checkInventory(order)

        branch "payment":
            authorizePayment(order)

        branch "risk":
            evaluateRisk(order)
    } join all

    createOrder(order)
}
~~~

Cú pháp trên chỉ minh họa ý tưởng. Mỗi DSL có thể chọn từ khóa khác nhau, nhưng cần thể hiện rõ điểm bắt đầu nhánh, nội dung từng nhánh và quy tắc đồng bộ.

Nhánh song song giúp giảm thời gian chờ khi các công việc độc lập, tăng khả năng tận dụng dịch vụ hoặc worker và thể hiện đúng bản chất của quy trình. Tuy nhiên, nó cũng đưa vào các vấn đề về đồng bộ, chia sẻ dữ liệu, lỗi một phần, timeout và thứ tự hoàn thành.

## 2. Song song, đồng thời và tuần tự

Ba khái niệm thường bị dùng lẫn nhau:

- **Tuần tự (sequential):** công việc sau chỉ bắt đầu khi công việc trước kết thúc.
- **Đồng thời (concurrent):** nhiều công việc có thể cùng tồn tại và tiến triển trong các khoảng thời gian chồng lấn.
- **Song song (parallel):** nhiều công việc thực sự được thực thi cùng một thời điểm, thường trên nhiều CPU core hoặc worker.

Một workflow có thể chạy đồng thời mà không chạy song song trên nhiều CPU. Ví dụ, một runtime bất đồng bộ có thể luân phiên xử lý nhiều tác vụ I/O trên một thread.

Với người thiết kế DSL, điều quan trọng là semantics của workflow: những nhánh nào được phép tiến triển độc lập, khi nào chúng đồng bộ và dữ liệu nào được chia sẻ. Runtime quyết định dùng thread, coroutine, event loop hay worker phân tán để thực hiện.

### 2.1. Trường hợp nên dùng nhánh song song

- Các kiểm tra độc lập có thể chạy cùng lúc.
- Một quy trình cần chờ nhiều bên phê duyệt.
- Nhiều nguồn dữ liệu cần được truy vấn đồng thời.
- Các tác vụ chuẩn bị có thể thực hiện trước khi một quyết định chung được đưa ra.
- Một workflow cần gửi công việc đến nhiều worker hoặc dịch vụ.

### 2.2. Trường hợp không nên tách nhánh

Nếu bước B cần kết quả của bước A, hai bước đó có quan hệ phụ thuộc và phải được nối tuần tự hoặc dùng một cơ chế truyền dữ liệu rõ ràng.

Ví dụ, không thể tính thuế cuối cùng trước khi biết giá trị hàng hóa nếu phép tính thuế phụ thuộc trực tiếp vào tổng tiền. Có thể chạy song song các phép tính không phụ thuộc nhau, nhưng phải đồng bộ trước khi tổng hợp.

### 2.3. Song song không tự động làm quy trình nhanh hơn

Nếu các nhánh cùng tranh chấp một database lock, một API có giới hạn tốc độ hoặc một worker pool nhỏ, việc tạo nhiều nhánh có thể làm thời gian xử lý tăng. Cần đo thời gian thực tế và xác định tài nguyên giới hạn.

## 3. Fork và Join

Hai cấu trúc nền tảng của nhánh song song là fork và join.

- **Fork:** tạo nhiều nhánh từ một điểm trong workflow.
- **Join:** đồng bộ các nhánh và quyết định khi nào luồng chính được tiếp tục.

Sơ đồ:

~~~text
              Start
                |
              Fork
           /    |    \
          v     v     v
       Branch A B     C
          |     |     |
          v     v     v
           \    |    /
               Join
                |
             Continue
~~~

### 3.1. Fork

Khi workflow đến fork, runtime tạo một execution path cho mỗi nhánh. Mỗi path có thể có branch ID riêng nhưng vẫn liên kết với cùng workflow instance và fork instance.

Fork cần xác định có bao nhiêu nhánh được tạo, các nhánh có bắt đầu ngay hay được đưa vào hàng đợi, dữ liệu nào được truyền cho từng nhánh, mỗi nhánh có deadline riêng không và có giới hạn số nhánh hoạt động đồng thời không.

### 3.2. Join

Join nhận thông tin hoàn tất từ các nhánh và áp dụng chính sách đồng bộ. Nó có thể chờ tất cả nhánh, chỉ cần một nhánh, một số lượng tối thiểu hoặc một điều kiện tùy chỉnh.

Join cần biết những nhánh nào thực sự được kích hoạt. Điều này đặc biệt quan trọng với nhánh điều kiện hoặc nhánh được tạo động.

### 3.3. Fork ID và branch ID

Một workflow có thể có nhiều fork, kể cả fork lồng nhau. Vì vậy, mỗi lần fork cần có định danh riêng. Branch ID xác định một nhánh thuộc fork nào.

Một cấu trúc trạng thái minh họa:

~~~text
ForkInstance {
    forkId
    workflowInstanceId
    expectedBranches
    completedBranches
    failedBranches
    joinPolicy
}
~~~

Không nên chỉ dùng tên nhánh để phân biệt nếu cùng một nhánh có thể chạy nhiều lần trong vòng lặp hoặc trong các instance khác nhau.

### 3.4. Completion signal

Khi nhánh kết thúc, runtime phát completion signal chứa branch ID, trạng thái, kết quả và metadata. Join dùng signal để cập nhật trạng thái tổng hợp.

Một nhánh hoàn tất không đồng nghĩa nhánh thành công. Cần phân biệt SUCCEEDED, FAILED, CANCELLED, TIMED_OUT hoặc trạng thái tương đương.

## 4. AND-split và AND-join

AND-split kích hoạt tất cả nhánh đầu ra. AND-join chờ tất cả nhánh được yêu cầu hoàn thành.

Ví dụ:

~~~text
parallel {
    branch "credit_check":
        checkCredit(customer)

    branch "identity_check":
        verifyIdentity(customer)

    branch "address_check":
        verifyAddress(customer)
} join all
~~~

Workflow chỉ tiếp tục khi cả ba nhánh hoàn tất theo chính sách all.

### 4.1. Điều kiện đồng bộ

Với AND-join, một điều kiện đơn giản là:

~~~text
completedCount == expectedCount
~~~

Nhưng trong workflow thực tế, expectedCount phải phản ánh đúng các nhánh được kích hoạt. Nếu một nhánh bị bỏ qua có chủ đích mà join vẫn chờ nó, workflow sẽ treo.

### 4.2. Hoàn tất thành công hay hoàn tất bất kỳ trạng thái nào?

Một join all có thể có nghĩa:
- Chờ mọi nhánh kết thúc, kể cả thành công hoặc thất bại, rồi đánh giá kết quả.
- Chỉ tiếp tục nếu mọi nhánh thành công.
- Hủy các nhánh còn lại ngay khi một nhánh thất bại.

Đây là các chính sách khác nhau. DSL cần phân biệt join all completed với join all succeeded hoặc cung cấp failure policy riêng.

### 4.3. AND-join trong sơ đồ quy trình

Trong workflow có nhiều đường đi, AND-join không nên đếm mọi đường có thể tồn tại trong sơ đồ. Nó cần biết những nhánh nào đã được kích hoạt trong lần chạy hiện tại. Nếu không, nhánh điều kiện không được chọn có thể khiến join đợi mãi.

## 5. XOR, OR và các kiểu phân nhánh khác

Không phải mọi điểm chia nhánh đều tạo nhiều công việc song song.

### 5.1. XOR-split

Exclusive OR (XOR) chọn đúng một nhánh theo điều kiện:

~~~text
choose {
    when order.total > 1000000:
        route "manual_review"

    otherwise:
        route "automatic_review"
}
~~~

Chỉ một đường được chọn, vì vậy đây là lựa chọn thay thế chứ không phải fan-out song song.

### 5.2. OR-split

Inclusive OR (OR) có thể kích hoạt một hoặc nhiều nhánh tùy điều kiện:

~~~text
parallel choose {
    when customer.isVip:
        branch "vip_service":
            prepareVipService(customer)

    when order.requiresGiftWrap:
        branch "gift_wrap":
            prepareGiftWrap(order)

    when order.requiresExportDocs:
        branch "export_docs":
            prepareExportDocuments(order)
} join activated all
~~~

Có thể không nhánh nào được kích hoạt nếu không có điều kiện đúng, trừ khi DSL quy định default branch.

### 5.3. OR-join

OR-join cần chờ tất cả nhánh đã được kích hoạt, không phải mọi nhánh có thể có trong định nghĩa workflow. Đây là lý do runtime phải theo dõi activation set.

### 5.4. Phân biệt bằng bảng

| Kiểu | Số nhánh được kích hoạt | Điều kiện tiếp tục |
|---|---:|---|
| XOR-split | Chính xác một | Nhánh được chọn hoàn tất |
| AND-split | Tất cả nhánh | Theo chính sách join all |
| OR-split | Một hoặc nhiều | Join chờ tất cả nhánh đã kích hoạt |
| Dynamic fan-out | Số lượng phụ thuộc dữ liệu | Join chờ tập nhánh được tạo hoặc theo policy |

### 5.5. Không dùng tên OR mơ hồ

Một DSL nên dùng tên policy rõ ràng như join activated all, join any success hoặc join quorum 3. Từ join any một mình có thể không nói rõ các nhánh còn lại bị hủy hay tiếp tục chạy.

## 6. Các chính sách Join

Join quyết định khi nào workflow được phép tiếp tục sau fork.

### 6.1. Join all

Chờ mọi nhánh được kích hoạt hoàn tất:

~~~text
parallel {
    branch "a": taskA()
    branch "b": taskB()
    branch "c": taskC()
} join all
~~~

Phù hợp khi mọi kết quả đều cần thiết.

### 6.2. Join all succeeded

Chỉ tiếp tục thành công nếu tất cả nhánh đều thành công. Khi có lỗi, workflow chuyển sang error path hoặc thực hiện compensation.

### 6.3. Join any completed

Tiếp tục khi có nhánh đầu tiên kết thúc, bất kể thành công hay thất bại. Cần xác định điều gì xảy ra với các nhánh còn lại.

### 6.4. Join first success

Tiếp tục khi có nhánh đầu tiên thành công. Nếu một nhánh thất bại, engine có thể chờ nhánh khác. Nếu tất cả thất bại, join chuyển sang lỗi.

### 6.5. Join quorum hoặc N-of-M

Chờ tối thiểu N nhánh thành công:

~~~text
parallel {
    branch "replica_a": readReplica("A")
    branch "replica_b": readReplica("B")
    branch "replica_c": readReplica("C")
} join quorum 2
~~~

Phù hợp với một số quy trình lấy ý kiến hoặc đọc dữ liệu từ nhiều replica. Quorum cần xác định rõ đếm thành công hay đếm mọi kết quả hoàn tất.

### 6.6. Join condition

DSL có thể cho phép biểu thức quyết định:

~~~text
join when successfulBranches >= 2
~~~

Điều kiện phải được đánh giá mỗi khi có completion signal. Nên giới hạn biểu thức để không gây tác dụng phụ hoặc truy cập trạng thái không được phép.

### 6.7. Join timeout

Một join có thể có thời hạn:

~~~text
join all timeout 30 minutes
~~~

Khi hết hạn, engine cần chính sách: fail, tiếp tục với kết quả một phần, bỏ nhánh chậm hoặc chuyển sang manual review.

### 6.8. Bảng lựa chọn

| Nhu cầu | Policy gợi ý |
|---|---|
| Cần đủ mọi kết quả | all succeeded |
| Chỉ cần một nguồn trả lời | first success |
| Cần phản hồi đầu tiên, bất kể trạng thái | any completed |
| Cần đa số hoặc số phiếu tối thiểu | quorum N |
| Chờ nhánh được kích hoạt theo điều kiện | activated all |
| Có deadline và chấp nhận kết quả thiếu | join condition kết hợp timeout |

## 7. Nhánh song song động (dynamic fan-out)

Một số workflow không biết trước số nhánh. Số nhánh có thể phụ thuộc số phần tử trong collection hoặc số người cần phê duyệt.

Ví dụ:

~~~text
parallel for reviewer in request.reviewers {
    branch reviewer.id:
        collectApproval(reviewer, request)
} join all
~~~

Nếu request có năm reviewer, runtime tạo năm branch instance.

### 7.1. Xác định tập nhánh

Dynamic fan-out cần xác định tập phần tử tại thời điểm fork. Có thể dùng snapshot của collection để tránh việc collection thay đổi giữa lúc tạo nhánh.

### 7.2. Nhánh không có phần tử

Nếu collection rỗng, join all có thể hoàn tất ngay vì không có nhánh nào cần chờ. Tuy nhiên, một số quy trình yêu cầu ít nhất một reviewer. Điều kiện đó nên được kiểm tra riêng.

### 7.3. Giới hạn concurrency

Nếu có hàng nghìn phần tử, tạo hàng nghìn task cùng lúc có thể làm cạn tài nguyên. Dùng giới hạn:

~~~text
parallel for item in items
    maxConcurrency = 20
{
    process(item)
} join all
~~~

Runtime có thể giữ toàn bộ nhánh logic nhưng chỉ chạy tối đa 20 nhánh tại một thời điểm.

### 7.4. Kết quả theo phần tử

Mỗi nhánh nên trả kết quả gắn với key ổn định, chẳng hạn reviewer ID hoặc item ID. Không nên phụ thuộc thứ tự hoàn thành để ghép kết quả vào đúng phần tử đầu vào.

### 7.5. Partial fan-out

Một số workflow có thể dừng tạo nhánh khi đạt một điều kiện, ví dụ đã có đủ số người phê duyệt. Khi đó, runtime cần lưu tập nhánh đã tạo và lý do không tạo các nhánh còn lại.

## 8. Phạm vi dữ liệu của nhánh

Khi fork, dữ liệu workflow được chia sẻ hoặc truyền vào các nhánh. Thiết kế phạm vi (scope) quyết định mỗi nhánh có thể đọc và ghi những giá trị nào.

### 8.1. Dữ liệu đầu vào dùng chung

Các nhánh thường cần đọc cùng một snapshot:

~~~text
parallel {
    branch "payment":
        authorizePayment(orderSnapshot)

    branch "inventory":
        reserveItems(orderSnapshot)
}
~~~

Nếu orderSnapshot bất biến, các nhánh có thể đọc an toàn mà không tranh chấp cập nhật.

### 8.2. Biến cục bộ của nhánh

Mỗi nhánh nên có local scope riêng:

~~~text
parallel {
    branch "payment":
        let paymentResult = authorizePayment(order)

    branch "inventory":
        let inventoryResult = reserveItems(order)
}
~~~

paymentResult không tự động tồn tại trong scope của inventory. Các kết quả cần được xuất qua output hoặc merge contract.

### 8.3. Output của nhánh

Một nhánh có thể khai báo output:

~~~text
branch "payment" {
    output payment = authorizePayment(order)
}
~~~

Join nhận các output theo branch ID và tạo một cấu trúc kết quả:

~~~text
ParallelResult {
    payment
    inventory
    risk
}
~~~

### 8.4. Tránh biến toàn cục mutable

Nếu mọi nhánh cùng ghi một biến global, kết quả có thể phụ thuộc thứ tự chạy. Thay vào đó, mỗi nhánh trả kết quả riêng rồi join thực hiện bước tổng hợp.

### 8.5. Snapshot và version

Fork có thể chụp snapshot của dữ liệu tại version V. Các nhánh đọc cùng snapshot giúp kết quả nhất quán. Nếu cần đọc dữ liệu mới nhất, phải quy định rõ và cân nhắc rằng mỗi nhánh có thể nhìn thấy phiên bản khác nhau.

## 9. Gộp kết quả và xử lý ghi đồng thời

Sau khi các nhánh hoàn tất, workflow có thể cần kết hợp output.

### 9.1. Merge theo trường

Nếu mỗi nhánh cập nhật một trường riêng, có thể gộp kết quả:

~~~text
merge {
    paymentStatus = payment.status
    inventoryStatus = inventory.status
    riskLevel = risk.level
}
~~~

### 9.2. Merge strategy

Nếu nhiều nhánh ghi cùng một key, DSL cần chiến lược rõ:

- **Reject conflict:** báo lỗi nếu có nhiều giá trị ghi cùng key.
- **First writer wins:** giữ giá trị ghi đầu tiên.
- **Last writer wins:** giữ giá trị ghi cuối theo một thứ tự được xác định.
- **Priority wins:** chọn kết quả từ nhánh có mức ưu tiên cao.
- **Reducer:** kết hợp các giá trị bằng phép gộp như sum, min, max hoặc custom reducer.
- **Manual resolution:** chuyển sang bước xử lý xung đột.

Last writer wins không nên dựa vào thời điểm thread thực sự ghi nếu cần kết quả tái hiện được. Nếu dùng thứ tự hoàn thành, kết quả có thể thay đổi giữa các lần chạy.

### 9.3. Reducer

Ví dụ cộng tổng kết quả:

~~~text
merge totalCost using sum(branch.totalCost)
~~~

Reducer nên có tính xác định và tốt nhất là kết hợp được (associative) nếu engine có thể gộp theo nhiều thứ tự.

### 9.4. Conflict detection

Một engine có thể ghi lại write set của từng nhánh. Khi join, nó phát hiện hai nhánh cùng sửa một key và áp dụng merge policy.

### 9.5. Optimistic concurrency

Nếu các nhánh cập nhật một record chung trong database, có thể dùng version check hoặc compare-and-set. Nhánh đọc version 4 chỉ commit nếu version vẫn là 4. Nếu một nhánh khác đã ghi version 5, cập nhật phải retry hoặc báo conflict.

### 9.6. Không có merge ngầm

Nếu hai nhánh cùng ghi một trường và DSL không quy định merge, runtime nên báo lỗi thay vì âm thầm chọn một giá trị không ổn định.

## 10. Đồng bộ và Barrier

Barrier là điểm mà các nhánh phải gặp nhau trước khi tiếp tục.

### 10.1. Barrier cơ bản

~~~text
parallel {
    branch "a": prepareA()
    branch "b": prepareB()
    branch "c": prepareC()
}
barrier
continueWorkflow()
~~~

Barrier chỉ mở khi điều kiện đồng bộ được thỏa.

### 10.2. Countdown barrier

Runtime có thể khởi tạo bộ đếm bằng số nhánh cần chờ. Mỗi completion signal giảm bộ đếm một lần. Khi về 0, barrier mở.

Phải chống việc một completion signal bị xử lý lặp làm bộ đếm giảm hai lần. Có thể lưu trạng thái hoàn tất theo branch ID và dùng cập nhật nguyên tử.

### 10.3. Barrier lặp

Một số workflow lặp qua nhiều vòng, mỗi vòng có barrier riêng. Cần gắn barrier với iteration ID để tín hiệu của vòng trước không mở nhầm barrier vòng sau.

### 10.4. Barrier và timeout

Barrier cần deadline hoặc chính sách timeout nếu một nhánh có thể bị treo. Nếu không, workflow có thể chờ vô hạn.

### 10.5. Join khác barrier ở mức trừu tượng

Barrier thường mô tả cơ chế đồng bộ các tác vụ đang chạy. Join trong workflow còn có thể áp dụng policy nghiệp vụ như quorum, first success, cancellation hoặc xử lý kết quả một phần.

## 11. Lỗi trong nhánh song song

Một nhánh có thể thất bại trong khi các nhánh khác vẫn đang chạy. Workflow phải quy định hành vi của cả fork.

### 11.1. Fail-fast

Khi một nhánh lỗi, engine đánh dấu fork thất bại và yêu cầu hủy các nhánh còn lại nếu có thể:

~~~text
parallel {
    branch "payment": authorizePayment(order)
    branch "inventory": reserveItems(order)
} join all failure failFast
~~~

Fail-fast giảm thời gian chờ nhưng không bảo đảm các tác vụ khác đã dừng ngay lập tức.

### 11.2. Wait-all then fail

Engine chờ tất cả nhánh kết thúc rồi tổng hợp lỗi. Cách này hữu ích khi cần thu thập mọi lỗi hoặc thực hiện cleanup trên từng nhánh.

### 11.3. Partial success

Workflow có thể chấp nhận kết quả một phần:

~~~text
join quorum 2
on insufficientResults:
    route "manual_review"
~~~

Cần định nghĩa kết quả nào được xem là đủ và các nhánh còn lại được xử lý ra sao.

### 11.4. Branch-level error handler

Mỗi nhánh có thể có handler riêng:

~~~text
branch "shipping_quote" {
    try:
        quoteShipping(order)
    catch Timeout:
        output quote = defaultQuote
}
~~~

Handler cục bộ có thể biến lỗi thành fallback result. Cần phân biệt fallback hợp lệ với việc che giấu lỗi nghiêm trọng.

### 11.5. Fork-level error handler

Một handler ở cấp fork có thể nhận danh sách lỗi, kết quả thành công và trạng thái từng nhánh. Nó quyết định retry, compensation, manual review hoặc fail workflow.

### 11.6. Tổng hợp lỗi

Khi nhiều nhánh lỗi, engine có thể tạo ParallelFailure gồm fork ID, danh sách branch ID, error code và message, thời điểm lỗi, retry count, các nhánh thành công và kết quả một phần.

Không nên chỉ giữ lỗi cuối cùng nếu cần điều tra nguyên nhân.

## 12. Timeout và deadline

Timeout giới hạn thời gian chờ của một nhánh hoặc toàn bộ fork.

### 12.1. Branch timeout

~~~text
branch "credit_check" {
    timeout = 15 seconds
    checkCredit(customer)
}
~~~

Nếu nhánh không hoàn tất trong thời gian cho phép, nó chuyển sang trạng thái timeout.

### 12.2. Fork deadline

~~~text
parallel {
    branch "a": taskA()
    branch "b": taskB()
} join all timeout 2 minutes
~~~

Deadline cấp fork giới hạn tổng thời gian chờ. Nhánh có timeout riêng có thể kết thúc trước deadline chung.

### 12.3. Timeout không đồng nghĩa với dừng tác vụ

Một timeout có thể chỉ có nghĩa runtime ngừng chờ kết quả. Service bên ngoài vẫn có thể tiếp tục xử lý request. Vì vậy, cancellation cần được gửi riêng và hệ thống đích cần hỗ trợ nếu muốn dừng thực sự.

### 12.4. Deadline propagation

Khi nhánh gọi dịch vụ con, deadline còn lại có thể được truyền xuống để tránh tác vụ con chạy lâu hơn workflow cha.

### 12.5. Clock và thời gian

Nên dùng clock abstraction để kiểm thử timeout. Với workflow phân tán, thời điểm giữa các máy có thể lệch; cần xác định deadline dựa trên nguồn thời gian đáng tin cậy và xử lý clock skew.

## 13. Cancellation và dừng các nhánh còn lại

Cancellation là yêu cầu chấm dứt công việc đang chạy.

### 13.1. Cooperative cancellation

Một nhánh kiểm tra cancellation token tại các điểm an toàn. Khi token được đánh dấu, nhánh dừng và thực hiện cleanup cần thiết.

### 13.2. Cancellation propagation

Nếu workflow cha bị hủy, cancellation có thể truyền đến các nhánh con và các tác vụ chúng khởi chạy.

### 13.3. Cancellation không phải rollback

Dừng một task không tự động đảo ngược database update, email đã gửi hoặc request đã tới hệ thống ngoài. Những tác dụng phụ đó cần transaction hoặc compensating action.

### 13.4. Grace period

Một runtime có thể cho nhánh một khoảng grace period để cleanup trước khi đánh dấu cancelled. Nếu quá thời hạn, nhánh có thể chuyển sang trạng thái cần can thiệp.

### 13.5. Cancellation race

Một nhánh có thể hoàn tất đúng lúc cancellation đến. Runtime cần quy định trạng thái cuối được quyết định theo thứ tự event, commit result hay cancellation acknowledgement. Cập nhật trạng thái phải nguyên tử để tránh hai trạng thái cuối cùng cùng được ghi.

## 14. Retry và idempotency trong nhánh song song

Một nhánh có thể retry độc lập với các nhánh khác.

### 14.1. Branch-level retry

~~~text
branch "payment" {
    retry {
        maxAttempts = 3
        backoff = exponential
        retryOn = [TIMEOUT, TEMPORARY_UNAVAILABLE]
    }
    authorizePayment(order)
}
~~~

Retry policy cần xác định lỗi nào được retry, số lần tối đa, khoảng chờ và thời điểm kết thúc.

### 14.2. Idempotency key

Nếu payment request bị timeout, runtime có thể không biết giao dịch đã được xử lý hay chưa. Gửi lại cùng idempotency key giúp dịch vụ đích nhận ra đây là cùng một thao tác logic nếu nó hỗ trợ cơ chế đó.

### 14.3. Retry toàn fork

Retry toàn fork có thể chạy lại cả nhánh đã thành công. Điều này nguy hiểm nếu các nhánh tạo tác dụng phụ. Chỉ dùng khi mọi nhánh idempotent hoặc runtime lưu và tái sử dụng kết quả nhánh đã hoàn tất.

### 14.4. Retry riêng nhánh lỗi

Một cách thường phù hợp hơn là chỉ retry nhánh lỗi, giữ kết quả đã commit của nhánh thành công. Cần lưu branch state và version để tiếp tục đúng.

### 14.5. Backoff và jitter

Nhiều nhánh cùng retry sau một lỗi hạ tầng có thể tạo tải đột biến. Exponential backoff và jitter giúp phân tán thời điểm retry.

## 15. Compensation và Saga

Khi nhiều nhánh thực hiện tác dụng phụ trên các hệ thống khác nhau, không thể giả định một database transaction có thể rollback tất cả.

Ví dụ:
- Nhánh payment giữ tiền.
- Nhánh inventory giữ hàng.
- Nhánh loyalty cộng điểm.

Nếu inventory thất bại sau khi payment đã giữ tiền, workflow cần hành động bù để giải phóng khoản giữ.

### 15.1. Compensating action

Mỗi action có thể có một hành động bù:

~~~text
reserveInventory(order)
compensate:
    releaseInventory(order)
~~~

Hành động bù là một thao tác nghiệp vụ mới, không phải xóa lịch sử hoặc rollback vật lý mọi hệ thống.

### 15.2. Saga

Saga chia quy trình thành các giao dịch cục bộ. Khi một bước thất bại, hệ thống chạy các compensation tương ứng theo policy.

### 15.3. Compensation theo nhánh

Mỗi nhánh thành công có thể đăng ký compensation. Nếu fork thất bại, runtime xác định những nhánh nào đã tạo tác dụng phụ và chạy bù cho chúng.

### 15.4. Thứ tự compensation

Một policy có thể chạy compensation theo thứ tự ngược với thứ tự commit hoặc theo dependency graph. Nếu các nhánh độc lập, compensation có thể chạy song song, nhưng vẫn cần kiểm soát tài nguyên và phụ thuộc.

### 15.5. Compensation cũng có thể thất bại

Nếu hành động bù lỗi, workflow cần lưu trạng thái COMPENSATION_REQUIRED hoặc tương đương, retry và cung cấp đường manual intervention. Không được đánh dấu toàn bộ quy trình đã rollback thành công khi compensation chưa hoàn tất.

## 16. Structured concurrency và vòng đời nhánh

Structured concurrency là nguyên tắc tổ chức tác vụ con trong một phạm vi cha rõ ràng. Các nhánh được tạo trong một block có vòng đời gắn với block đó.

Một mô hình:

~~~text
parallel {
    branch "a": taskA()
    branch "b": taskB()
} join all
~~~

Block chỉ hoàn tất khi policy join được thỏa và các nhánh thuộc phạm vi đã được xử lý theo quy tắc.

### 16.1. Không để task mồ côi

Nếu một nhánh tạo task con nhưng kết thúc mà không theo dõi task đó, công việc có thể tiếp tục sau khi workflow cha đã hoàn tất. Runtime nên yêu cầu task con thuộc một scope hoặc được detach một cách tường minh.

### 16.2. Parent-child cancellation

Hủy workflow cha thường cần truyền xuống các nhánh con. Ngược lại, một nhánh con thất bại không nhất thiết hủy cha; điều đó phụ thuộc failure policy.

### 16.3. Resource cleanup

Scope cần bảo đảm giải phóng lock, connection, temporary file hoặc lease khi nhánh kết thúc, bị hủy hoặc timeout.

### 16.4. Scope lồng nhau

Một nhánh có thể tạo fork con. Fork con phải được join hoặc detach theo semantics rõ ràng trước khi nhánh cha kết thúc.

## 17. Giới hạn concurrency và điều phối tài nguyên

Tạo quá nhiều nhánh có thể gây quá tải hệ thống.

### 17.1. Max concurrency

~~~text
parallel for item in items
    maxConcurrency = 10
{
    process(item)
}
~~~

Tại một thời điểm tối đa mười nhánh được thực thi. Các nhánh còn lại chờ trong queue.

### 17.2. Semaphore

Semaphore giới hạn số tác vụ cùng sử dụng một tài nguyên. Ví dụ, chỉ cho phép tối đa năm request đồng thời tới dịch vụ thanh toán.

### 17.3. Worker pool

Runtime có thể dùng worker pool để xử lý nhánh. Kích thước pool và queue capacity cần được cấu hình theo workload.

### 17.4. Backpressure

Nếu nhánh được tạo nhanh hơn khả năng xử lý, runtime cần backpressure hoặc giới hạn fan-out. Nếu không, queue và bộ nhớ có thể tăng không giới hạn.

### 17.5. Resource isolation

Một nhánh chạy truy vấn nặng không nên chiếm toàn bộ tài nguyên khiến các nhánh khác bị đói. Có thể dùng quota CPU, memory, connection hoặc execution slots.

### 17.6. Công bằng

Nếu một workflow liên tục tạo nhiều nhánh, nó có thể chiếm worker của workflow khác. Scheduler có thể dùng fair queueing, tenant quota hoặc weighted scheduling.

## 18. Deadlock và dependency giữa các nhánh

Deadlock xảy ra khi các nhánh chờ lẫn nhau hoặc chờ tài nguyên mà không nhánh nào có thể giải phóng.

### 18.1. Chờ vòng tròn

Ví dụ:
- Nhánh A giữ lock X và chờ lock Y.
- Nhánh B giữ lock Y và chờ lock X.

Cả hai không thể tiến triển.

### 18.2. Join lồng sai

Một nhánh chờ fork con hoàn tất, nhưng fork con lại chờ một tín hiệu chỉ nhánh cha có thể phát sau khi join. Đây là dependency cycle.

### 18.3. Exhausted worker pool

Nếu mọi worker đều đang chờ một task con được xếp hàng nhưng không còn worker rảnh để chạy task con, hệ thống có thể bị starvation hoặc deadlock tùy runtime.

### 18.4. Biện pháp phòng tránh

- Xác định dependency graph trước khi chạy.
- Quy định thứ tự lấy lock.
- Không giữ lock khi chờ dịch vụ hoặc human task lâu.
- Dùng async wait thay vì block worker.
- Giới hạn độ sâu fork.
- Dùng timeout và deadlock detection khi phù hợp.
- Tránh vòng phụ thuộc giữa các branch output.

### 18.5. Phân biệt deadlock và tác vụ chậm

Một nhánh chậm nhưng vẫn tiến triển không phải deadlock. Monitoring cần quan sát trạng thái chờ, dependency và thời gian không có tiến triển để phân biệt.

## 19. Thứ tự hoàn thành và tính xác định

Các nhánh song song có thể hoàn tất theo thứ tự khác với thứ tự khai báo.

Ví dụ, nhánh B chạy 100 ms còn nhánh A chạy 2 giây. B có thể hoàn tất trước A dù A được viết trước.

### 19.1. Completion order

Completion order là thứ tự nhánh thực sự hoàn tất. Nó phụ thuộc tài nguyên, network, scheduling và dữ liệu.

### 19.2. Declaration order

Declaration order là thứ tự nhánh trong DSL. Nó có thể được dùng để hiển thị kết quả hoặc tie-break nhưng không đồng nghĩa với completion order.

### 19.3. Kết quả ổn định

Nếu kết quả được ghép thành list, nên sắp xếp theo branch key hoặc input order nếu muốn đầu ra xác định. Không nên mặc định kết quả theo thời điểm hoàn tất.

### 19.4. Deterministic merge

Reducer nên có kết quả ổn định. Với phép cộng số thực, thứ tự cộng có thể ảnh hưởng sai số làm tròn. Nếu cần kết quả chính xác, dùng Decimal hoặc một cách tổng hợp có semantics xác định.

### 19.5. Event ordering

Các event phát từ nhánh khác nhau có thể đến join theo thứ tự bất kỳ. Nếu thứ tự event có ý nghĩa, cần sequence number, causal metadata hoặc một bước sắp xếp dựa trên quy tắc rõ ràng.

## 20. Persistence, checkpoint và resume

Workflow dài hạn có thể bị dừng hoặc runtime restart trong khi một số nhánh đang chờ.

### 20.1. Trạng thái fork bền vững

Runtime cần lưu workflow instance ID, fork ID, branch ID và trạng thái từng nhánh, join policy, kết quả đã hoàn tất, retry count và deadline, cancellation state, cùng version của workflow definition.

### 20.2. Checkpoint

Checkpoint ghi trạng thái đủ để khôi phục fork:

~~~text
ParallelCheckpoint {
    forkId
    expectedBranchIds
    branchStates
    branchOutputs
    joinPolicy
    completedCount
    workflowVersion
}
~~~

### 20.3. Resume

Khi runtime khởi động lại:
1. Đọc checkpoint.
2. Xác định nhánh đã thành công, thất bại hoặc đang chạy.
3. Đối chiếu các action đang chờ với outbox hoặc hệ thống ngoài.
4. Khôi phục deadline và retry policy.
5. Tiếp tục các nhánh chưa hoàn tất.
6. Đánh giá lại điều kiện join.

### 20.4. Không chạy trùng nhánh đã commit

Nếu runtime crash sau khi nhánh gọi dịch vụ ngoài thành công nhưng trước khi lưu kết quả, resume có thể chạy lại action. Idempotency key hoặc deduplication cần được dùng để tránh tác dụng phụ trùng.

### 20.5. Workflow version

Nếu định nghĩa workflow thay đổi trong khi fork đang chạy, cần xác định instance tiếp tục dùng version cũ hay được migrate. Migration phải xử lý cả branch state, join policy và output schema.

## 21. Bảo mật và ranh giới tin cậy

Các nhánh có thể chạy trên worker hoặc service khác nhau. Không nên mặc định mọi nhánh đều có quyền giống nhau.

### 21.1. Capability theo nhánh

Có thể cấp quyền riêng:

~~~text
branch "read_profile" {
    capabilities = [ReadCustomerProfile]
    loadProfile(customerId)
}

branch "charge_payment" {
    capabilities = [CreatePayment]
    charge(order)
}
~~~

### 21.2. Least privilege

Mỗi nhánh chỉ nhận quyền cần thiết cho công việc. Nhánh đọc hồ sơ không cần quyền thu tiền.

### 21.3. Tenant context

Tenant ID hoặc security context cần được truyền và xác thực ở runtime. Không dựa vào biến do nhánh tự đặt.

### 21.4. Secret propagation

Không đưa secret vào mọi branch context nếu chỉ một nhánh cần. Dùng secret reference hoặc capability truy cập an toàn.

### 21.5. Log và dữ liệu nhạy cảm

Trace nên ghi branch ID, trạng thái và mã lỗi cần thiết nhưng tránh ghi token, thông tin thanh toán hoặc dữ liệu cá nhân không cần thiết.

## 22. Quan sát và vận hành nhánh song song

Khi nhiều nhánh chạy đồng thời, người vận hành cần thấy tiến độ của từng nhánh và quan hệ giữa chúng.

### 22.1. Fork dashboard

Một dashboard có thể hiển thị workflow instance và fork ID, join policy, danh sách branch ID, trạng thái hiện tại, thời gian bắt đầu và kết thúc, retry count, deadline, kết quả hoặc lỗi gần nhất.

### 22.2. Distributed tracing

Dùng trace ID chung cho workflow, span riêng cho fork và mỗi branch. Parent-child span giúp xác định nhánh nào đang chậm.

### 22.3. Metrics

Một số metric hữu ích:
- Số fork đang mở.
- Số branch đang chạy hoặc chờ.
- Thời gian fork đến join.
- Branch duration theo loại.
- Timeout và failure rate.
- Số lần retry.
- Queue depth.
- Mức sử dụng worker.
- Tỷ lệ join hoàn tất với kết quả một phần.

### 22.4. Correlation ID

Mọi log của nhánh nên mang workflow ID, fork ID và branch ID. Nếu gọi dịch vụ ngoài, truyền correlation ID để liên kết log giữa các hệ thống.

### 22.5. Manual intervention

Một fork có thể bị treo do một nhánh bên ngoài không phản hồi. Người vận hành cần biết có thể retry, bỏ nhánh, cung cấp kết quả thay thế hay hủy workflow theo policy nào. Mọi thao tác can thiệp cần được audit.

## 23. Thiết kế cú pháp DSL cho nhánh song song

Cú pháp cần diễn đạt được fork, branch, join và lỗi một cách rõ ràng.

### 23.1. Block song song tường minh

~~~text
parallel {
    branch "a":
        taskA()

    branch "b":
        taskB()
} join all
~~~

Ưu điểm là dễ đọc, dễ gắn metadata và dễ mở rộng.

### 23.2. Parallel map

~~~text
parallel for item in items
    maxConcurrency = 8
{
    process(item)
} join all
~~~

Phù hợp với fan-out theo collection.

### 23.3. Join policy tường minh

~~~text
} join quorum 3
  timeout 5 minutes
  onFailure compensate
~~~

Các thuộc tính có thể được đặt trong một block policy riêng nếu cú pháp dài.

### 23.4. Output mapping

~~~text
} join all as results

let payment = results["payment"]
let inventory = results["inventory"]
~~~

DSL cần quy định kiểu của results và hành vi khi một nhánh thất bại.

### 23.5. Type checking

Parser có thể nhận diện cú pháp; type checker cần xác nhận nhánh có output tương thích không, join policy có hợp lệ với số nhánh không, quorum có lớn hơn số nhánh tối đa không, output key có duy nhất không, reducer nhận đúng kiểu không và branch có dùng biến ngoài scope không.

### 23.6. Static analysis

Workbench có thể cảnh báo:
- Fork có nhánh không bao giờ hoàn tất.
- Join chờ nhánh không thể được kích hoạt.
- Hai nhánh cùng ghi một biến.
- Không có timeout cho một lời gọi có thể chờ vô hạn.
- Có dependency cycle giữa các nhánh.

## 24. Kiểm thử nhánh song song

Kiểm thử concurrency khó hơn kiểm thử tuần tự vì thứ tự hoàn thành có thể thay đổi. Nên kiểm tra semantics thay vì giả định một lịch chạy duy nhất.

### 24.1. Kiểm thử fork cơ bản

Xác nhận tất cả nhánh được tạo, mỗi nhánh có branch ID đúng và input được truyền đúng.

### 24.2. Kiểm thử join all

Cho các nhánh hoàn tất theo nhiều thứ tự. Join chỉ mở khi tất cả nhánh được yêu cầu đã kết thúc.

### 24.3. Kiểm thử join any và quorum

Kiểm tra nhánh đầu tiên thành công, nhánh đầu tiên thất bại, đủ quorum, không thể đạt quorum và các nhánh còn lại được hủy hay tiếp tục theo policy.

### 24.4. Kiểm thử dynamic fan-out

Dùng collection rỗng, một phần tử, nhiều phần tử và collection thay đổi trong lúc fork. Xác nhận expected branch set được chụp đúng.

### 24.5. Kiểm thử merge conflict

Cho hai nhánh ghi cùng key. Xác nhận conflict được báo hoặc merge policy cho kết quả xác định.

### 24.6. Kiểm thử lỗi và timeout

Kiểm tra một nhánh lỗi, nhiều nhánh lỗi, timeout, cancellation đến đúng lúc nhánh hoàn tất và compensation thất bại.

### 24.7. Kiểm thử retry và crash recovery

Giả lập crash trước khi action bắt đầu, sau khi action ngoài thành công nhưng trước khi lưu kết quả, sau khi một số nhánh commit và trong khi join đang cập nhật trạng thái. Xác nhận resume không làm mất hoặc lặp tác dụng phụ ngoài ý muốn.

### 24.8. Kiểm thử deadlock và giới hạn tài nguyên

Tạo dependency cycle có kiểm soát, queue đầy, worker pool nhỏ và fork lồng nhau. Xác nhận timeout, backpressure hoặc deadlock detection hoạt động.

### 24.9. Kiểm thử xác định

Dùng scheduler giả hoặc điều khiển thứ tự hoàn tất để chạy cùng input với nhiều interleaving. Kết quả cuối cần tuân theo semantics đã công bố.

### 24.10. Kiểm thử tải

Đo throughput, latency, memory, queue depth và branch duration khi có nhiều workflow cùng fan-out. Kiểm tra fairness giữa tenant hoặc workflow.

## 25. Những lỗi thiết kế thường gặp

### 25.1. Nhầm song song với lựa chọn điều kiện

XOR chọn một nhánh; AND-split kích hoạt nhiều nhánh. Dùng sai cấu trúc có thể làm bỏ sót công việc hoặc chạy trùng.

### 25.2. Join chờ nhánh chưa từng được kích hoạt

Join phải dựa trên tập nhánh thực tế được tạo, đặc biệt với OR-split và dynamic fan-out.

### 25.3. Chia sẻ biến mutable giữa các nhánh

Các nhánh có thể ghi đè nhau. Hãy dùng local output và merge policy.

### 25.4. Dựa vào completion order để gộp kết quả

Thứ tự hoàn thành không ổn định. Dùng branch key hoặc reducer xác định.

### 25.5. Hủy task nhưng nghĩ rằng đã rollback

Cancellation không đảo ngược tác dụng phụ đã xảy ra. Cần transaction hoặc compensation.

### 25.6. Retry toàn bộ fork không kiểm soát

Nhánh đã thành công có thể chạy lại và tạo tác dụng phụ trùng. Lưu kết quả và retry riêng nhánh lỗi khi phù hợp.

### 25.7. Không giới hạn fan-out

Một collection lớn có thể tạo quá nhiều nhánh. Dùng maxConcurrency, queue limit và backpressure.

### 25.8. Giữ lock khi chờ join lâu

Lock có thể ngăn nhánh khác tiến triển và gây deadlock. Không giữ transaction hoặc lock trong khi chờ dịch vụ hoặc người phê duyệt.

### 25.9. Không lưu branch state

Sau restart, engine không biết nhánh nào đã chạy hoặc đã commit. Cần checkpoint và idempotency.

### 25.10. Không theo dõi fork và branch ID

Log thiếu correlation làm việc điều tra rất khó. Mỗi event cần liên kết với workflow, fork và branch.

## 26. Quy trình thiết kế nhánh song song

Một quy trình có thể thực hiện như sau:

1. Xác định những công việc thực sự độc lập và có thể chạy đồng thời.
2. Vẽ dependency graph để biết điểm fork và join.
3. Chọn kiểu split: AND, XOR, OR hoặc dynamic fan-out.
4. Chọn join policy: all, all succeeded, first success, quorum hoặc condition.
5. Xác định input snapshot, branch scope và output schema.
6. Chọn merge strategy và xử lý ghi xung đột.
7. Quy định failure policy, timeout, cancellation, retry và compensation.
8. Đặt maxConcurrency, quota và backpressure.
9. Kiểm tra nested fork, lock ordering và dependency cycle.
10. Thiết kế checkpoint, resume, branch identity và idempotency.
11. Bổ sung trace, metric, audit và manual intervention.
12. Viết kiểm thử với nhiều thứ tự hoàn tất, lỗi, timeout và crash.
13. Đo hiệu năng trên workload có quy mô gần thực tế.

## 27. Ví dụ tổng hợp: xử lý đơn hàng với ba nhánh

Một đơn hàng cần kiểm tra tồn kho, thanh toán và rủi ro trước khi được xác nhận.

~~~text
workflow "confirm_order" {
    let orderSnapshot = loadOrder(orderId)

    parallel {
        branch "inventory" {
            output reservation =
                reserveInventory(orderSnapshot.items)

            compensate:
                releaseInventory(reservation)
        }

        branch "payment" {
            output payment =
                authorizePayment(
                    orderSnapshot.total,
                    idempotencyKey = workflow.id + ":payment"
                )

            compensate:
                voidPayment(payment)
        }

        branch "risk" {
            output risk =
                evaluateRisk(orderSnapshot.customerId)
        }
    } join all succeeded
      timeout 90 seconds
      onFailure compensateCompletedBranches

    if risk.result == "LOW"
       and payment.status == "AUTHORIZED"
       and inventory.status == "RESERVED" {
        createOrder(
            orderSnapshot,
            reservation,
            payment
        )
    } else {
        route "manual_review"
    }
}
~~~

Cú pháp trên minh họa một policy trong đó cả ba nhánh phải thành công trước khi workflow đánh giá kết quả chung.

### 27.1. Fork

Khi đến block parallel, runtime tạo ba branch instance với cùng workflow ID và fork ID riêng. Mỗi nhánh nhận dữ liệu cần thiết từ orderSnapshot.

### 27.2. Thực thi độc lập

Nhánh inventory gọi dịch vụ kho. Nhánh payment gọi cổng thanh toán. Nhánh risk tính điểm rủi ro. Chúng có thể hoàn tất theo thứ tự bất kỳ.

### 27.3. Join

Join all succeeded chờ cả ba nhánh thành công. Nếu một nhánh lỗi hoặc timeout, workflow áp dụng onFailure policy.

### 27.4. Compensation

Nếu payment đã authorize nhưng inventory thất bại, runtime có thể gọi voidPayment. Nếu inventory đã reserve, runtime có thể releaseInventory. Compensation cần biết nhánh nào đã thực hiện tác dụng phụ và kết quả nào đã được commit.

### 27.5. Kết quả và quyết định

Sau join, workflow sử dụng output có tên để kiểm tra điều kiện. Việc dùng branch key giúp không phụ thuộc thứ tự hoàn thành.

### 27.6. Recovery

Nếu runtime restart sau khi payment authorize nhưng trước khi lưu kết quả, idempotency key giúp request retry không tạo authorization trùng nếu cổng thanh toán hỗ trợ. Checkpoint cho biết nhánh nào đã hoàn tất và nhánh nào cần tiếp tục.

### 27.7. Quan sát

Dashboard có thể hiển thị ba nhánh, thời gian mỗi nhánh, trạng thái, retry count và lý do fork chưa join. Trace liên kết các request đến kho, thanh toán và dịch vụ rủi ro.

## 28. Bài tập tự kiểm tra

### Bài 1: Fork và Join

Một workflow cần kiểm tra hồ sơ, kiểm tra tín dụng và xác minh địa chỉ đồng thời. Hãy xác định điểm fork, số nhánh, dữ liệu đầu vào và join policy.

### Bài 2: AND và XOR

Giải thích sự khác nhau giữa AND-split và XOR-split. Đưa ra một tình huống nghiệp vụ phù hợp cho từng loại.

### Bài 3: Join policy

Một quy trình lấy xác nhận từ năm dịch vụ và chỉ cần ba dịch vụ thành công. Hãy chọn join policy và xác định cách xử lý nếu chỉ có hai dịch vụ thành công trước deadline.

### Bài 4: Dynamic fan-out

Một yêu cầu cần gửi đến danh sách reviewer có kích thước thay đổi. Hãy thiết kế parallel-for, maxConcurrency, branch ID và output mapping.

### Bài 5: Shared state

Hai nhánh cùng ghi trường decision. Hãy giải thích race condition và đề xuất local output, reducer hoặc conflict policy.

### Bài 6: Timeout và cancellation

Một nhánh thanh toán timeout trong khi nhánh kho đã giữ hàng. Hãy mô tả khác biệt giữa timeout, cancellation và compensation.

### Bài 7: Retry và idempotency

Một request bên ngoài có thể đã được xử lý dù client nhận timeout. Hãy thiết kế idempotency key và cách resume nhánh an toàn.

### Bài 8: Deadlock

Một fork lồng nhau có các nhánh chờ kết quả của nhau. Hãy vẽ dependency cycle và đề xuất cách tái cấu trúc.

### Bài 9: Deterministic merge

Ba nhánh trả về các giá trị số theo thứ tự hoàn thành ngẫu nhiên. Hãy thiết kế reducer và kiểu số để kết quả ổn định.

### Bài 10: Kiểm thử

Lập kế hoạch kiểm thử cho một workflow có dynamic fan-out, quorum join, timeout, compensation và crash recovery. Nêu các interleaving quan trọng cần mô phỏng.

## Kết luận

Nhánh song song cho phép DSL quy trình mô tả các công việc độc lập được khởi chạy từ một điểm fork và đồng bộ tại join. Thiết kế cần phân biệt AND, XOR, OR và dynamic fan-out; xác định rõ join policy; đồng thời quản lý scope, output và cách gộp dữ liệu. Vì các nhánh có thể hoàn tất theo thứ tự bất kỳ, runtime cần kiểm soát ghi đồng thời, lỗi, timeout, cancellation, retry và compensation. Với workflow dài hạn, fork và branch state phải được lưu để checkpoint và resume an toàn. Giới hạn concurrency, backpressure, structured lifecycle, trace và kiểm thử nhiều interleaving giúp hệ thống duy trì tính nhất quán khi nhiều nhánh chạy đồng thời hoặc khi một phần quy trình gặp sự cố.
