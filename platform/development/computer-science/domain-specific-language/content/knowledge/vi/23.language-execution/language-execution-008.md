# Đồng thời

## 1. Đồng thời trong thực thi DSL

Một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) thường mô tả các công việc có thể gồm nhiều bước: đọc dữ liệu, kiểm tra điều kiện, gọi dịch vụ, cập nhật trạng thái hoặc tạo đầu ra. Khi quy mô công việc tăng, hệ thống có thể cần thực hiện nhiều tác vụ trong cùng một khoảng thời gian để tận dụng CPU, I/O hoặc tài nguyên phân tán.

**Đồng thời (concurrency)** là khả năng tổ chức nhiều tác vụ sao cho tiến trình của chúng có thể xen kẽ hoặc cùng tiến triển trong một khoảng thời gian. Nếu phần cứng có nhiều lõi hoặc nhiều bộ xử lý, một số tác vụ còn có thể chạy thực sự cùng lúc; đó là **song song (parallelism)**.

Hai khái niệm có liên quan nhưng không đồng nghĩa:

- Concurrency mô tả cách chương trình tổ chức nhiều công việc đang tiến triển.
- Parallelism mô tả việc nhiều công việc thực sự được thực thi cùng thời điểm trên các tài nguyên xử lý khác nhau.

Một runtime chạy trên một luồng có thể hỗ trợ concurrency bằng cách chuyển đổi giữa các tác vụ khi một tác vụ chờ I/O. Một runtime nhiều lõi có thể thực hiện cả concurrency và parallelism.

Ví dụ DSL giả định:

~~~text
workflow "daily-report" {
    task load_orders {
        read "orders.csv"
    }

    task load_customers {
        read "customers.csv"
    }

    task build_report {
        depends_on load_orders
        depends_on load_customers
        join_data
        write "report.csv"
    }
}
~~~

Hai tác vụ đọc dữ liệu độc lập có thể được lập lịch đồng thời. Tác vụ build_report chỉ được bắt đầu sau khi cả hai đầu vào sẵn sàng. DSL mô tả quan hệ phụ thuộc; runtime quyết định thời điểm và tài nguyên để chạy từng tác vụ.

Đồng thời là một phần của ngữ nghĩa thực thi. DSL cần xác định rõ tác vụ nào có thể chạy đồng thời, dữ liệu nào được chia sẻ, cách phối hợp, cách xử lý lỗi và trạng thái nào được xem là hoàn thành.

## 2. Concurrency và parallelism

Hai tác vụ có thể đồng thời mà không chạy song song. Ví dụ, trên một luồng, runtime bắt đầu tác vụ A, chuyển sang B khi A chờ mạng, rồi quay lại A khi dữ liệu đến. Cả hai cùng tiến triển theo thời gian nhưng tại mỗi thời điểm chỉ có một luồng thực thi lệnh.

Ngược lại, khi A và B chạy trên hai lõi CPU khác nhau, chúng có thể thực thi cùng lúc.

| Tiêu chí | Concurrency | Parallelism |
|---|---|---|
| Ý nghĩa | Nhiều tác vụ cùng tiến triển | Nhiều tác vụ thực sự chạy đồng thời |
| Mục tiêu thường gặp | Quản lý nhiều công việc đang chờ hoặc hoạt động | Tăng thông lượng hoặc giảm thời gian tính toán |
| Yêu cầu phần cứng | Có thể chạy trên một lõi | Cần nhiều tài nguyên xử lý thực thi đồng thời |
| Ví dụ | Một event loop điều phối nhiều request I/O | Chia một phép tính thành nhiều phần chạy trên nhiều lõi |
| Rủi ro | Tranh chấp trạng thái, thứ tự sự kiện khó đoán | Thêm race condition và chi phí đồng bộ hóa |

Một DSL có thể cung cấp mức concurrency độc lập với số lõi. Ví dụ max_parallelism 8 là giới hạn số tác vụ có thể hoạt động đồng thời; runtime có thể thực hiện chúng trên ít hơn tám luồng tùy tài nguyên.

Không nên suy luận rằng khai báo concurrent luôn làm chương trình nhanh hơn. Nếu các tác vụ phụ thuộc nhau, tranh chấp cùng một tài nguyên hoặc quá nhỏ so với chi phí điều phối, thực thi đồng thời có thể làm tăng overhead.

## 3. Vì sao DSL cần hỗ trợ đồng thời?

Các trường hợp phổ biến:

1. **Tác vụ I/O độc lập:** đọc nhiều tệp, truy vấn nhiều dịch vụ hoặc chờ nhiều phản hồi mạng.
2. **Xử lý batch:** xử lý các bản ghi hoặc partition độc lập.
3. **Workflow:** chạy nhiều nhánh không phụ thuộc nhau trước khi hợp nhất kết quả.
4. **Tính toán:** chia công việc lớn thành các phần có thể thực hiện song song.
5. **Phản hồi tương tác:** xử lý nhiều request hoặc session mà không chặn toàn bộ runtime.
6. **Pipeline streaming:** tiếp nhận, biến đổi và phát dữ liệu qua nhiều stage.
7. **Tác vụ nền:** thực hiện công việc dài hạn trong khi các tác vụ khác tiếp tục.

Ví dụ DSL có thể mô tả nhiều nguồn:

~~~text
parallel {
    fetch inventory
    fetch prices
    fetch promotions
}
combine inventory, prices, promotions
~~~

Nếu ba thao tác fetch không phụ thuộc nhau, runtime có thể khởi chạy chúng cùng lúc. Bước combine cần đợi đủ kết quả theo chính sách đã khai báo.

Hỗ trợ đồng thời cần đi kèm giới hạn và quy tắc rõ ràng. Nếu DSL chỉ cho phép khởi chạy vô hạn tác vụ, hệ thống có thể hết bộ nhớ, cạn kết nối hoặc tạo tải vượt khả năng của dịch vụ ngoài.

## 4. Các mô hình thực thi đồng thời

Không có một mô hình duy nhất phù hợp với mọi DSL. Runtime có thể chọn một mô hình hoặc kết hợp nhiều mô hình.

### 4.1. Thread-based concurrency

Mỗi tác vụ hoặc nhóm tác vụ được thực hiện trên một luồng. Các luồng có thể chạy trên nhiều lõi.

Ưu điểm:

- Phù hợp với thư viện blocking và một số workload CPU-bound.
- Mô hình lập trình quen thuộc với nhiều nền tảng.
- Có thể tận dụng nhiều lõi khi công việc độc lập.

Hạn chế:

- Mỗi luồng có chi phí stack và quản lý.
- Chia sẻ bộ nhớ làm phát sinh race condition.
- Số lượng luồng quá lớn gây context switching và áp lực tài nguyên.
- Deadlock có thể xuất hiện khi khóa được dùng sai.

### 4.2. Event loop

Event loop thường dùng một hoặc một số ít luồng để xử lý các sự kiện sẵn sàng. Khi tác vụ chờ I/O bất đồng bộ, event loop có thể xử lý tác vụ khác.

Ưu điểm:

- Có thể phục vụ nhiều tác vụ I/O với số luồng nhỏ.
- Giảm nhu cầu tạo một luồng cho mỗi request.
- Dễ tổ chức khi các thao tác đều hỗ trợ API non-blocking.

Hạn chế:

- Một callback hoặc đoạn xử lý blocking dài có thể chặn event loop.
- Cần quản lý trạng thái bất đồng bộ và lỗi.
- Code có thể khó đọc nếu chuỗi callback không được cấu trúc tốt.

### 4.3. Task-based concurrency

Task là đơn vị công việc được scheduler quản lý. Task có thể không gắn cố định với một luồng; scheduler chọn worker thread phù hợp khi task sẵn sàng chạy.

Mô hình task thường thích hợp với DSL vì người dùng mô tả công việc và phụ thuộc, còn runtime quản lý thread pool, hàng đợi và lịch thực thi.

### 4.4. Actor model

Actor là thực thể có trạng thái riêng và nhận message. Các actor không trực tiếp sửa trạng thái nội bộ của nhau; chúng trao đổi thông qua message.

Mô hình này giúp giảm chia sẻ bộ nhớ trực tiếp. Tuy nhiên, vẫn cần xử lý thứ tự message, mailbox, lỗi actor và vòng đời hệ thống.

### 4.5. Data parallelism

Data parallelism chia dữ liệu thành nhiều phần và áp dụng cùng một phép biến đổi lên từng phần:

~~~text
parallel_map orders {
    calculate_total(order)
}
~~~

Runtime chia orders thành partition, xử lý từng partition và hợp nhất kết quả theo quy tắc. Mô hình này phù hợp với batch và dữ liệu lớn, nhưng cần định nghĩa thứ tự đầu ra, xử lý phần tử lỗi và tính chất của hàm được áp dụng.

### 4.6. Distributed execution

Các task có thể chạy trên nhiều process hoặc máy khác nhau. Khi đó, runtime cần quản lý truyền dữ liệu, retry, network failure, serialization, partition và trạng thái task từ xa.

Distributed execution có thể dùng cùng mô hình task của DSL, nhưng các giả định về bộ nhớ chia sẻ và chi phí giao tiếp thay đổi đáng kể.

## 5. Khai báo concurrency trong DSL

DSL có thể biểu diễn đồng thời bằng nhiều cấu trúc cú pháp. Cấu trúc nên phản ánh ý nghĩa của miền thay vì buộc người dùng quản lý thread trực tiếp.

### 5.1. Khối parallel

~~~text
parallel {
    task_a()
    task_b()
    task_c()
}
~~~

Khối có thể yêu cầu runtime khởi chạy các tác vụ con đồng thời và đợi chúng hoàn tất trước khi tiếp tục. Cần quy định khối có trả kết quả hay không và cách tổng hợp lỗi.

### 5.2. Tác vụ bất đồng bộ và await

~~~text
let response = await fetch_customer(customer_id)
process response
~~~

await biểu thị điểm mà tác vụ hiện tại cần kết quả. Nếu kết quả chưa sẵn sàng, runtime có thể tạm dừng tác vụ để cho công việc khác tiến triển. await không nhất thiết chặn thread; điều đó phụ thuộc implementation.

### 5.3. Future hoặc Promise

~~~text
let inventory_future = fetch_inventory()
let price_future = fetch_price()

let inventory = await inventory_future
let price = await price_future
calculate(inventory, price)
~~~

Future/Promise đại diện cho kết quả có thể có trong tương lai. Hai lời gọi được khởi chạy trước khi await giúp chúng có cơ hội tiến triển đồng thời.

### 5.4. Fork và join

~~~text
let left = fork calculate_left()
let right = fork calculate_right()

let result = join(left, right)
~~~

fork tạo một đơn vị công việc độc lập; join đợi kết quả hoặc trạng thái kết thúc. DSL cần quy định join có thể chờ vô hạn hay có timeout, và lỗi của một nhánh được truyền lên như thế nào.

### 5.5. Map song song

~~~text
results = parallel_map(records, max_workers = 4) {
    transform(record)
}
~~~

Runtime áp dụng cùng một phép biến đổi cho nhiều phần tử. Cần định nghĩa thứ tự kết quả, giới hạn worker, hành vi khi một phần tử lỗi và cách hủy các phần tử còn lại.

Các ví dụ trên là cú pháp giả định. Một DSL thực tế có thể chọn một tập cấu trúc nhỏ hơn để tránh nhiều cách biểu diễn cùng một ý nghĩa.

## 6. Mô hình tác vụ và quan hệ phụ thuộc

Một workflow đồng thời thường được biểu diễn như đồ thị tác vụ có hướng. Mỗi node là một task; cạnh A -> B có nghĩa B phụ thuộc vào A.

Ví dụ:

~~~text
          Load Orders
              |
              v
          Validate
              |
              v
           Enrich
              |
              v
            Output

Load Customers -----> Enrich
~~~

Load Orders và Load Customers có thể chạy đồng thời. Enrich chỉ chạy khi cả hai đã hoàn thành thành công. Output đợi Enrich.

### 6.1. Dependency edge

Một dependency có thể mang ý nghĩa:

- B chỉ được bắt đầu sau khi A hoàn tất.
- B cần kết quả của A làm input.
- B chỉ chạy nếu A thành công.
- B chạy khi A kết thúc bất kể thành công hay thất bại, ví dụ cleanup.

Không nên gộp mọi loại quan hệ vào một cạnh không có kiểu. Một DSL workflow có thể cần phân biệt success dependency, completion dependency và data dependency.

### 6.2. DAG và chu trình

Nhiều workflow được thiết kế như DAG (Directed Acyclic Graph), tức đồ thị có hướng không chu trình. DAG giúp scheduler xác định thứ tự khả thi và tìm các task sẵn sàng chạy.

Nếu có chu trình phụ thuộc, chẳng hạn A chờ B và B chờ A, không task nào có thể bắt đầu. Compiler hoặc workflow validator nên phát hiện chu trình trước khi thực thi, trừ khi DSL có ngữ nghĩa vòng lặp hoặc feedback loop được định nghĩa riêng.

### 6.3. Ready queue

Task sẵn sàng khi mọi điều kiện phụ thuộc cần thiết đã thỏa mãn. Scheduler có thể đưa task đó vào ready queue. Khi worker rảnh, nó lấy một task phù hợp để chạy.

### 6.4. Critical path

Critical path là đường phụ thuộc có tổng thời lượng lớn nhất trong một DAG theo mô hình thời gian đã ước lượng. Đường này đặt giới hạn dưới cho thời gian hoàn thành workflow nếu không có thêm ràng buộc tài nguyên.

Trace và metrics có thể giúp nhận ra task nào đang quyết định thời gian hoàn tất. Tuy nhiên, thời lượng ước lượng không bảo đảm thời lượng thực tế vì còn có queueing, contention và biến động hệ thống.

## 7. Scheduler và chính sách lập lịch

Scheduler quyết định task nào được chạy, khi nào và trên worker nào.

### 7.1. Thread pool

Thread pool duy trì một tập worker thread để thực hiện task. Task được đưa vào hàng đợi; worker rảnh sẽ nhận task tiếp theo.

Lợi ích:

- Giới hạn số thread.
- Tái sử dụng worker.
- Tập trung quản lý hàng đợi và shutdown.

Một pool duy nhất có thể không phù hợp với mọi loại công việc. Task CPU-bound và I/O-bound có đặc tính khác nhau; hệ thống có thể dùng pool riêng hoặc scheduler có khả năng phân loại.

### 7.2. Giới hạn concurrency

DSL có thể cho phép:

~~~text
execution {
    max_parallelism 8
}
~~~

Giới hạn này kiểm soát số task được thực thi đồng thời trong phạm vi quy định. Cần nói rõ nó áp dụng cho một block, một workflow, một process hay toàn hệ thống.

### 7.3. Fairness

Fair scheduler cố gắng không để một task hoặc nhóm task chiếm toàn bộ tài nguyên trong thời gian dài. Chính sách có thể dựa trên round-robin, priority, quota hoặc weighted scheduling.

Ưu tiên cao có thể giúp công việc quan trọng hoàn tất sớm, nhưng nếu không có giới hạn, task ưu tiên thấp có thể bị starvation.

### 7.4. Priority

~~~text
task "urgent-alert" priority high {
    send_alert()
}
~~~

Priority là gợi ý hoặc ràng buộc cho scheduler tùy thiết kế. Không nên hứa rằng priority high luôn chạy trước mọi task khác nếu scheduler còn phải tuân theo dependency, quota và fairness.

### 7.5. Work stealing

Trong một số scheduler, worker rảnh có thể lấy task từ hàng đợi của worker khác. Cách này giúp cân bằng tải khi các nhánh có thời lượng khác nhau. Nó phù hợp với nhiều task nhỏ, nhưng cần xử lý locality, task affinity và chi phí di chuyển.

### 7.6. Task granularity

Task quá nhỏ làm chi phí tạo, xếp hàng và đồng bộ lớn hơn công việc. Task quá lớn làm giảm khả năng cân bằng tải và khó phản hồi khi hủy. DSL hoặc runtime cần chọn kích thước partition và task granularity phù hợp với workload.

## 8. Chia sẻ trạng thái và race condition

Race condition xảy ra khi kết quả phụ thuộc vào thứ tự hoặc thời điểm các tác vụ truy cập và thay đổi trạng thái dùng chung.

Ví dụ:

~~~text
shared counter = 0

parallel {
    repeat 1000 {
        counter = counter + 1
    }
    repeat 1000 {
        counter = counter + 1
    }
}
~~~

Nếu phép tăng không phải thao tác nguyên tử, hai task có thể cùng đọc một giá trị rồi ghi đè kết quả của nhau. Kết quả cuối có thể nhỏ hơn 2000.

### 8.1. Read-modify-write

Phép tăng thường gồm ba bước:

1. Đọc counter.
2. Cộng 1.
3. Ghi kết quả.

Nếu hai task xen kẽ các bước, một lần cập nhật có thể bị mất. Việc một dòng DSL trông như một câu lệnh đơn không bảo đảm runtime thực hiện nó nguyên tử.

### 8.2. Data race

Data race thường được mô tả là hai luồng truy cập cùng vị trí bộ nhớ, có ít nhất một thao tác ghi, và không có đồng bộ hóa phù hợp. Tùy mô hình bộ nhớ, hành vi có thể không xác định hoặc vi phạm hợp đồng ngôn ngữ.

Không phải mọi race condition đều là data race. Một hệ thống có thể dùng message queue an toàn bộ nhớ nhưng vẫn có race logic, ví dụ hai task cùng đặt chỗ cuối cùng cho một đơn hàng.

### 8.3. Immutable data

Một cách giảm race là dùng dữ liệu bất biến sau khi tạo. Nhiều task có thể đọc cùng giá trị mà không phải phối hợp việc ghi.

~~~text
let config = immutable {
    region = "ap-southeast"
    retries = 3
}

parallel {
    deploy_service_a(config)
    deploy_service_b(config)
}
~~~

Nếu cấu hình không thể thay đổi, hai task có thể dùng chung mà không có tranh chấp ghi.

### 8.4. Ownership

Một mô hình khác là mỗi task sở hữu trạng thái riêng. Task chỉ truyền kết quả cho task khác qua message hoặc giá trị trả về. Việc giới hạn quyền ghi giúp compiler hoặc runtime kiểm tra xung đột sớm hơn.

### 8.5. Local state

Biến local thuộc một lần thực thi task có thể được giữ riêng cho task đó. Tuy nhiên, nếu biến tham chiếu đến một đối tượng mutable dùng chung, bản thân tham chiếu local không loại bỏ race condition.

## 9. Đồng bộ hóa

Đồng bộ hóa (synchronization) điều phối quyền truy cập trạng thái hoặc thứ tự giữa các tác vụ.

### 9.1. Mutex và lock

Mutex bảo đảm chỉ một task hoặc thread giữ khóa tại một thời điểm:

~~~text
with lock account_lock {
    balance = balance - amount
}
~~~

Khối được bảo vệ không bị thực thi đồng thời bởi các bên cùng dùng lock. Lock cần được giải phóng trong cả trường hợp thành công lẫn lỗi; cấu trúc with/finally hoặc RAII có thể giúp bảo đảm điều đó.

### 9.2. Semaphore

Semaphore giới hạn số tác vụ cùng truy cập một tài nguyên:

~~~text
with semaphore database_slots(5) {
    query_database()
}
~~~

Ví dụ cho phép tối đa năm task đồng thời vào vùng truy cập database. Semaphore đếm khác mutex: nó có thể cho phép nhiều bên giữ permit cùng lúc.

### 9.3. Atomic operation

Atomic operation thực hiện một cập nhật như một đơn vị không thể bị quan sát ở trạng thái nửa chừng theo mô hình bộ nhớ tương ứng:

~~~text
atomic_increment(counter)
~~~

Atomic phù hợp với thao tác nhỏ như bộ đếm hoặc cập nhật trạng thái đơn giản. Với invariant gồm nhiều trường, một atomic operation đơn lẻ có thể không đủ.

### 9.4. Barrier

Barrier làm các task chờ tại một điểm cho đến khi đủ nhóm task đến:

~~~text
parallel {
    compute_partition_a()
    compute_partition_b()
    compute_partition_c()
    barrier
    merge_partitions()
}
~~~

Barrier hữu ích khi một giai đoạn cần toàn bộ phần trước hoàn thành. Nếu một task lỗi hoặc không bao giờ đến barrier, các task khác có thể bị chờ; cần chính sách lỗi và timeout.

### 9.5. Condition variable

Condition variable cho phép task chờ đến khi một điều kiện trạng thái được thỏa mãn. Việc chờ cần gắn với mutex hoặc cơ chế đồng bộ tương ứng, và điều kiện phải được kiểm tra lại sau khi thức dậy.

DSL cấp cao thường nên cung cấp abstraction như await condition hoặc wait_for thay vì để người dùng thao tác trực tiếp với primitive nếu miền không cần chi tiết đó.

### 9.6. Channel và message passing

Channel truyền message giữa producer và consumer:

~~~text
channel orders capacity 100

parallel {
    producer {
        send orders, read_next_order()
    }
    consumer {
        for each order from orders {
            process(order)
        }
    }
}
~~~

Channel giúp giảm chia sẻ bộ nhớ trực tiếp. Cần quy định channel có FIFO không, send có block khi đầy không, close được xử lý thế nào và consumer nhận lỗi ra sao.

## 10. Deadlock, livelock và starvation

Đồng bộ hóa có thể tạo ra những trạng thái mà công việc không tiến triển như mong muốn.

### 10.1. Deadlock

Deadlock xảy ra khi các task chờ nhau theo vòng phụ thuộc tài nguyên.

Ví dụ:

~~~text
Task A holds lock X and waits for lock Y
Task B holds lock Y and waits for lock X
~~~

Không task nào có thể tiếp tục vì mỗi task đang giữ tài nguyên mà task còn lại cần.

Các cách giảm nguy cơ:

- Quy định thứ tự lấy lock thống nhất.
- Giảm vùng giữ lock.
- Tránh chờ I/O khi đang giữ lock.
- Dùng timeout hoặc try-lock khi phù hợp.
- Hạn chế số lock lồng nhau.

Timeout không tự sửa mọi deadlock; nó chỉ giúp một thao tác thoát khỏi chờ vô hạn nếu có thể xử lý trạng thái sau timeout an toàn.

### 10.2. Livelock

Livelock xảy ra khi các task vẫn hoạt động và phản ứng với nhau nhưng không hoàn thành công việc. Ví dụ hai task liên tục nhường khóa cho nhau rồi thử lại đồng thời.

Backoff có jitter hoặc cơ chế phân xử có thể giảm hiện tượng này.

### 10.3. Starvation

Starvation xảy ra khi một task liên tục không được cấp tài nguyên hoặc không được scheduler chọn chạy. Priority không công bằng, lock contention hoặc hàng đợi không hợp lý có thể gây ra tình trạng này.

Metrics về thời gian chờ, số lần bị trì hoãn và độ tuổi task giúp phát hiện starvation.

### 10.4. Dependency deadlock

Trong workflow, một task có thể chờ task khác mà task kia lại phụ thuộc vào task đầu tiên. Validator có thể phát hiện chu trình dependency trong DAG trước khi scheduler chạy.

## 11. Memory model và visibility

Khi nhiều luồng cùng truy cập bộ nhớ, không chỉ thứ tự thao tác mà cả khả năng nhìn thấy cập nhật cũng quan trọng.

Một luồng ghi giá trị nhưng luồng khác không có quan hệ đồng bộ phù hợp có thể chưa quan sát được cập nhật theo kỳ vọng của người viết chương trình. Compiler và CPU cũng có thể sắp xếp lại một số thao tác khi điều đó được phép bởi mô hình bộ nhớ.

### 11.1. Happens-before

Happens-before là quan hệ thứ tự đảm bảo các thao tác trước một điểm đồng bộ được nhìn thấy phù hợp bởi thao tác sau điểm đó.

Ví dụ, nếu task A ghi dữ liệu rồi publish message qua một channel có bảo đảm đồng bộ, task B nhận message có thể dựa vào hợp đồng của channel để thấy dữ liệu đã được công bố.

### 11.2. Visibility và atomicity

- Visibility nói về việc cập nhật từ một task có được task khác nhìn thấy không.
- Atomicity nói về việc thao tác có thể bị quan sát ở trạng thái dở dang hay không.

Một trường volatile có thể hỗ trợ visibility theo mô hình của nền tảng, nhưng không làm cho phép tăng nhiều bước trở thành atomic. Ngược lại, atomic increment bảo đảm cập nhật nguyên tử nhưng không tự bảo vệ invariant phức tạp trên nhiều trường.

### 11.3. DSL abstraction

Nếu DSL cung cấp shared state, cần chỉ rõ mô hình bộ nhớ và các cơ chế đồng bộ hợp lệ. Nếu DSL hướng đến người dùng miền không chuyên về concurrency, có thể giới hạn chia sẻ mutable state và ưu tiên immutable value, task input/output hoặc channel.

## 12. Determinism và thứ tự kết quả

Một chương trình đồng thời có thể cho kết quả khác nhau giữa các lần chạy nếu kết quả phụ thuộc lịch scheduler hoặc thứ tự cập nhật.

### 12.1. Deterministic execution

Thực thi xác định (deterministic) nghĩa là với cùng đầu vào và điều kiện được quy định, chương trình cho cùng kết quả quan sát được. Một số DSL cần tính xác định để hỗ trợ tái lập, kiểm toán hoặc kiểm thử.

### 12.2. Thứ tự hoàn thành và thứ tự đầu ra

Giả sử parallel_map xử lý các phần tử theo thứ tự đầu vào:

~~~text
results = parallel_map([A, B, C]) {
    slow_transform(item)
}
~~~

Task B có thể hoàn thành trước A. DSL cần quy định results có giữ thứ tự đầu vào hay phản ánh thứ tự hoàn thành.

Hai chính sách phổ biến:

- Ordered result: giữ thứ tự phần tử nguồn, dù task hoàn thành không theo thứ tự.
- Completion order: phát kết quả ngay khi task hoàn thành.

Ordered result thuận tiện cho tính xác định nhưng có thể phải buffer kết quả đã xong trong khi chờ phần tử chậm hơn.

### 12.3. Race trong phép tổng hợp

Nếu nhiều task cộng vào một biến dùng chung, thứ tự cập nhật có thể không xác định. Với số thực dấu phẩy động, phép cộng không kết hợp chính xác do làm tròn; thay đổi thứ tự có thể tạo sai khác nhỏ ở kết quả.

Một cách khác là mỗi task tạo subtotal riêng rồi runtime kết hợp theo cây reduction hoặc thứ tự cố định. Chính sách reduction cần được công bố nếu kết quả phải tái lập.

### 12.4. Deterministic scheduling

Một runtime có thể cung cấp chế độ lập lịch xác định cho debugging hoặc replay. Tuy nhiên, khóa thứ tự có thể giảm hiệu năng và không nhất thiết tái hiện chính xác mọi tác động bên ngoài như thời gian phản hồi mạng.

### 12.5. Nondeterminism có chủ đích

Một số ứng dụng chấp nhận thứ tự hoàn thành không xác định để tối đa thông lượng. Khi đó, DSL nên thể hiện rõ nơi kết quả có thể không theo thứ tự và cung cấp cách yêu cầu ordering nếu cần.

## 13. Async, Future và Promise

Async/await là cách biểu diễn công việc bất đồng bộ bằng cấu trúc gần với code tuần tự.

### 13.1. Async task

Một hàm async trả về một đối tượng đại diện cho kết quả tương lai thay vì trả kết quả ngay:

~~~text
async function load_customer(id) {
    return await customer_service.get(id)
}
~~~

Lời gọi hàm có thể khởi chạy hoặc tạo task tùy semantics của DSL. Đặc tả cần nói rõ công việc bắt đầu khi gọi, khi await hay khi scheduler nhận task.

### 13.2. Await

~~~text
let customer = await load_customer(customer_id)
~~~

await tạm dừng task hiện tại cho đến khi kết quả sẵn sàng. Một runtime non-blocking có thể giải phóng thread để thực hiện task khác.

### 13.3. Khởi chạy nhiều future

~~~text
let inventory = fetch_inventory()
let pricing = fetch_pricing()
let promotions = fetch_promotions()

let values = await all(inventory, pricing, promotions)
calculate_quote(values)
~~~

Các tác vụ được khởi chạy trước khi đợi kết quả tổng hợp. all có thể hoàn tất khi tất cả thành công hoặc thất bại theo chính sách được định nghĩa.

### 13.4. Await tuần tự và khởi chạy đồng thời

Nếu viết:

~~~text
let a = await fetch_a()
let b = await fetch_b()
~~~

và lời gọi chỉ bắt đầu khi được await, hai thao tác có thể diễn ra tuần tự. Nếu lời gọi tạo task ngay, chúng có thể tiến triển đồng thời dù await theo thứ tự. Đây là khác biệt cần nêu rõ trong semantics của DSL.

### 13.5. Future composition

Các future có thể được kết hợp bằng:

- all: đợi tất cả.
- any: đợi task đầu tiên hoàn thành theo tiêu chí.
- race: trả về kết quả đầu tiên theo chính sách.
- map: biến đổi kết quả khi sẵn sàng.
- recover: chuyển lỗi thành kết quả thay thế.

Tên và semantics khác nhau giữa thư viện. DSL cần định nghĩa rõ future bị hủy hay tiếp tục khi một future khác thắng.

## 14. Structured concurrency

Structured concurrency tổ chức task con theo phạm vi vòng đời của task cha. Task cha thường không thể hoàn thành bình thường khi các task con còn hoạt động mà chưa được xử lý.

Ví dụ:

~~~text
task "prepare-report" {
    parallel {
        load_orders()
        load_customers()
    }
    build_report()
}
~~~

Khối parallel là một scope. Khi scope kết thúc, các task con phải đã hoàn thành, thất bại hoặc được hủy theo chính sách.

Lợi ích:

- Vòng đời task dễ theo dõi.
- Lỗi của task con có thể được truyền về task cha.
- Hủy có thể lan truyền theo cây task.
- Giảm task mồ côi chạy sau khi workflow cha đã kết thúc.
- Dễ quản lý resource và cleanup.

### 14.1. Task scope

Mỗi scope có thể chứa task con, cancellation token, deadline và chính sách lỗi. Scope chỉ hoàn tất khi các task con đạt trạng thái cuối theo hợp đồng.

### 14.2. Unstructured task

Một task được khởi chạy và tách khỏi phạm vi của caller có thể sống lâu hơn workflow đã tạo nó. Điều này có thể cần cho công việc nền, nhưng cần quản lý rõ bằng service hoặc supervisor có vòng đời riêng.

### 14.3. Parent-child cancellation

Khi task cha bị hủy, runtime có thể gửi tín hiệu hủy đến các task con. Task con cần hợp tác bằng cách kiểm tra cancellation hoặc gọi API hỗ trợ hủy.

Cancellation không bảo đảm mọi thao tác bên ngoài đã dừng. Một request mạng có thể đã được server xử lý dù client ngừng chờ.

## 15. Xử lý lỗi trong tác vụ đồng thời

Khi nhiều task chạy đồng thời, lỗi có thể xuất hiện ở một hoặc nhiều nhánh. DSL cần quy định cách tổng hợp kết quả.

### 15.1. Fail-fast

Khi một task lỗi, scope có thể đánh dấu thất bại và yêu cầu hủy các task còn lại:

~~~text
parallel fail_fast {
    load_orders()
    load_customers()
    load_products()
}
~~~

Fail-fast phù hợp khi kết quả chỉ hợp lệ nếu mọi nhánh thành công. Runtime vẫn cần đợi hoặc thu hồi task con theo cách an toàn trước khi kết thúc scope.

### 15.2. Collect all errors

Một scope khác có thể đợi mọi task kết thúc rồi tổng hợp tất cả lỗi:

~~~text
parallel collect_errors {
    validate_customers()
    validate_orders()
    validate_products()
}
~~~

Cách này hữu ích khi các kiểm tra độc lập và người dùng cần xem tất cả vấn đề trong một lượt.

### 15.3. Partial success

Với xử lý batch, một số partition có thể thành công và một số thất bại. Runtime có thể trả trạng thái partial success cùng danh sách kết quả và lỗi theo partition.

Không nên báo toàn bộ workflow thành công nếu dữ liệu bị bỏ qua mà không ghi nhận. Trạng thái cuối cần thể hiện mức hoàn thành thực tế.

### 15.4. Exception aggregation

Nếu nhiều task lỗi, runtime có thể giữ lỗi đầu tiên làm primary error và đính kèm các lỗi còn lại, hoặc trả một collection có cấu trúc. Không nên làm mất lỗi của các task khác chỉ vì một lỗi được phát hiện trước.

### 15.5. Retry

Retry có thể áp dụng cho lỗi tạm thời, nhưng cần giới hạn số lần và thời gian. Nếu task có side effect, cần idempotency key hoặc cơ chế xác định trạng thái trước khi chạy lại.

### 15.6. Cleanup

Task có thể cần đóng file, release lock hoặc trả connection về pool khi thành công, lỗi hoặc bị hủy. Cleanup nên được bảo đảm bằng finally, defer hoặc resource scope tương đương.

## 16. Cancellation, timeout và deadline

Một task đồng thời có thể cần dừng trước khi hoàn thành.

### 16.1. Cancellation

Cancellation là yêu cầu dừng công việc. Nó có thể đến từ người dùng, task cha, timeout hoặc chính sách hệ thống.

~~~text
let task = start long_operation()
cancel task
~~~

Runtime cần định nghĩa cancellation cooperative hay preemptive. Cooperative cancellation thường an toàn hơn: task kiểm tra tín hiệu tại các điểm phù hợp và tự dừng.

### 16.2. Timeout

~~~text
let result = await fetch_data() timeout 5s
~~~

Timeout giới hạn thời gian chờ. Khi hết thời gian, future có thể bị hủy hoặc caller nhận timeout trong khi tác vụ nền vẫn tiếp tục. Hai hành vi này cần được phân biệt.

### 16.3. Deadline

Deadline là thời điểm tuyệt đối mà task hoặc scope phải hoàn tất. Các task con có thể nhận cùng deadline hoặc một phần ngân sách thời gian còn lại.

### 16.4. Hủy và side effect

Hủy một task không tự động hoàn tác những thao tác đã thực hiện. Nếu task đã ghi dữ liệu hoặc gửi yêu cầu đến dịch vụ, cần transaction, compensation hoặc idempotency để phục hồi trạng thái.

### 16.5. Cleanup khi hủy

Runtime nên:

- Ngừng cấp công việc mới cho task đã hủy.
- Truyền cancellation đến các tác vụ con theo chính sách.
- Đóng hoặc giải phóng tài nguyên.
- Ghi trạng thái CANCELLED riêng với FAILED.
- Thu thập lỗi cleanup nếu có.

## 17. Backpressure và giới hạn hàng đợi

Trong pipeline streaming, producer có thể tạo dữ liệu nhanh hơn consumer xử lý. Nếu không giới hạn, hàng đợi tăng liên tục và có thể làm hết bộ nhớ.

Backpressure là cơ chế điều tiết tốc độ producer theo khả năng tiếp nhận của consumer.

### 17.1. Bounded queue

~~~text
channel events capacity 500
~~~

Khi queue đầy, send có thể chờ, từ chối dữ liệu hoặc áp dụng chính sách drop. DSL cần nêu rõ hành vi.

### 17.2. Các chính sách khi đầy

- Block producer cho đến khi có chỗ.
- Reject message và trả lỗi.
- Drop newest.
- Drop oldest.
- Spill dữ liệu ra storage.
- Giảm tốc hoặc tạm dừng upstream.

Mỗi chính sách có ảnh hưởng khác nhau đến tính đầy đủ và độ trễ dữ liệu.

### 17.3. Demand-based flow

Consumer có thể yêu cầu số lượng phần tử mà nó sẵn sàng xử lý. Producer chỉ phát dữ liệu theo demand. Mô hình này giúp kiểm soát memory và làm rõ nhịp truyền dữ liệu.

### 17.4. Buffer và batching

Batching gom nhiều phần tử thành một nhóm để giảm overhead. Batch quá lớn tăng latency và memory; batch quá nhỏ làm tăng số lần gọi và chi phí điều phối.

### 17.5. Metrics

Nên quan sát queue depth, thời gian chờ, số message bị drop, throughput, consumer lag và tỷ lệ retry để phát hiện backpressure không hiệu quả.

## 18. Tài nguyên và giới hạn đồng thời

Concurrency sử dụng tài nguyên dùng chung như thread, connection, file handle, memory, CPU và quota dịch vụ.

### 18.1. Resource pool

Một pool quản lý số lượng tài nguyên hữu hạn:

~~~text
database_pool {
    max_connections 20
}
~~~

Task phải lấy connection trước khi truy vấn và trả lại sau khi dùng. Pool giúp tránh mở kết nối vô hạn.

### 18.2. Semaphore cho quota

Nếu API chỉ cho phép tối đa mười request đồng thời, semaphore có thể giới hạn số request đang hoạt động.

### 18.3. CPU-bound và I/O-bound

CPU-bound task tiêu thụ thời gian xử lý; I/O-bound task thường chờ thiết bị hoặc dịch vụ. Số worker phù hợp có thể khác nhau. Tăng worker cho CPU-bound quá mức có thể chỉ làm tăng context switching; I/O-bound có thể hưởng lợi từ nhiều task đang chờ nếu runtime non-blocking hoặc có đủ worker.

### 18.4. Resource leak

Nếu task bị hủy hoặc lỗi mà không release connection, lock hoặc file, tài nguyên sẽ bị giữ lại. Sau nhiều lần chạy, pool có thể cạn dù mỗi workflow riêng lẻ trông có vẻ nhỏ.

### 18.5. Admission control

Admission control quyết định có nhận thêm task hay không dựa trên tải và quota. Runtime có thể từ chối, xếp hàng hoặc trì hoãn task mới để bảo vệ hệ thống.

## 19. Transaction và tính nhất quán khi chạy đồng thời

Khi nhiều task cùng cập nhật dữ liệu, transaction và isolation level ảnh hưởng kết quả.

### 19.1. Lost update

Hai task đọc cùng một giá trị, mỗi task tính giá trị mới và ghi lại. Một lần ghi có thể đè lần còn lại. Đây là lost update.

### 19.2. Isolation

Database cung cấp các mức isolation khác nhau, chẳng hạn read committed, repeatable read hoặc serializable. Mỗi mức đưa ra bảo đảm khác nhau về những thay đổi mà transaction có thể quan sát.

DSL không nên che giấu hoàn toàn mức isolation nếu người dùng cần hiểu tính nhất quán của workflow. Có thể cho phép khai báo policy hoặc dùng mặc định được tài liệu hóa.

### 19.3. Optimistic concurrency control

Một thao tác đọc phiên bản hiện tại rồi chỉ ghi nếu phiên bản chưa thay đổi. Nếu có xung đột, task có thể đọc lại và thử lại theo chính sách.

### 19.4. Serializable workflow

Một workflow có thể yêu cầu kết quả tương đương với một thứ tự tuần tự nào đó, dù runtime thực thi đồng thời. Đây là bảo đảm mạnh và có thể cần khóa hoặc transaction phù hợp.

### 19.5. Distributed transaction

Khi task cập nhật nhiều dịch vụ độc lập, một transaction ACID đơn lẻ thường không bao phủ toàn bộ hệ thống. Có thể dùng saga với các thao tác bù trừ, nhưng compensation không phải rollback hoàn hảo.

### 19.6. Side effect ordering

Nếu hai task gửi thông báo hoặc cập nhật tài nguyên, thứ tự có thể quan trọng. DSL cần biểu diễn dependency khi thứ tự là yêu cầu nghiệp vụ thay vì để scheduler quyết định tùy ý.

## 20. Deterministic reduction và xử lý dữ liệu song song

Một phép reduce tổng hợp kết quả từ nhiều phần:

~~~text
total = parallel_reduce(amounts, sum)
~~~

Để phép reduction có thể được phân phối an toàn, phép kết hợp thường cần có tính kết hợp và phần tử đơn vị phù hợp. Với số nguyên có giới hạn, overflow có thể làm tính kết hợp không còn đúng theo semantics. Với số thực, sai số làm tròn có thể khiến thứ tự kết hợp thay đổi kết quả.

### 20.1. Associative operation

Một phép toán kết hợp thỏa:

~~~text
(a op b) op c = a op (b op c)
~~~

Khi điều kiện này đúng, runtime có thể chia dữ liệu thành partition, tính subtotal rồi kết hợp theo cây.

### 20.2. Commutative operation

Một phép toán giao hoán thỏa:

~~~text
a op b = b op a
~~~

Tính giao hoán giúp thứ tự phần tử ít ảnh hưởng hơn, nhưng không thay thế yêu cầu kết hợp khi runtime thay đổi cách nhóm phép toán.

### 20.3. Order-sensitive aggregation

Các thao tác như nối chuỗi, lấy phần tử đầu tiên hoặc dựng danh sách có thể phụ thuộc thứ tự. Runtime cần giữ ordering hoặc yêu cầu người dùng chọn phép tổng hợp có semantics xác định.

### 20.4. Stable partitioning

Nếu cùng một key luôn được đưa vào cùng partition theo quy tắc ổn định, hệ thống có thể giảm giao tiếp và hỗ trợ kết quả nhất quán hơn. Tuy nhiên, thay đổi số partition hoặc hash strategy có thể thay đổi vị trí dữ liệu; không nên coi partition ID là định danh nghiệp vụ.

## 21. Observability và debugging concurrency

Lỗi đồng thời thường khó tái hiện vì phụ thuộc thời điểm, tải và lịch scheduler. Cần quan sát được vòng đời task và quan hệ phụ thuộc.

### 21.1. Task ID và parent ID

Mỗi task nên có ID; task con có thể giữ parent ID hoặc scope ID. Điều này giúp nhóm các sự kiện thuộc cùng workflow.

### 21.2. Timeline

Timeline cho thấy thời điểm task được tạo, xếp hàng, bắt đầu, chờ, tiếp tục và kết thúc. Nó giúp phân biệt thời gian thực thi với thời gian chờ scheduler hoặc I/O.

### 21.3. Trace context

Context có thể truyền qua lời gọi bất đồng bộ để liên kết log và trace giữa các task. Khi task chuyển sang worker khác, trace context vẫn cần được giữ.

### 21.4. Metrics

Các chỉ số hữu ích:

- Số task đang chạy và đang chờ.
- Queue depth và queue wait time.
- Task throughput.
- Thời lượng theo task type.
- Số lần timeout, retry và cancellation.
- Lock wait time và contention.
- Số connection đang dùng.
- Số task bị reject do quota.

### 21.5. Race detector và stress test

Một số runtime hoặc công cụ có thể phát hiện data race. Stress test tăng mức concurrency và lặp lại workload để tăng khả năng gặp interleaving hiếm.

Không tìm thấy race trong một lần chạy không chứng minh chương trình không có race. Cần kết hợp phân tích, thiết kế ownership và kiểm thử.

### 21.6. Deterministic replay

Một runtime có thể ghi lại lịch sự kiện đủ chi tiết để tái phát lại một execution. Replay hữu ích cho debugging nhưng khó với hệ thống phụ thuộc mạng, thời gian thực, random source hoặc dịch vụ ngoài. Cần ghi hoặc giả lập các nguồn nondeterministic liên quan.

## 22. Kiểm thử DSL đồng thời

Kiểm thử đồng thời cần xác nhận kết quả và các bảo đảm về thứ tự, giới hạn tài nguyên, hủy và lỗi.

### 22.1. Kiểm thử dependency

Xác nhận task phụ thuộc không bắt đầu trước khi điều kiện dependency thỏa mãn. Đồng thời, các task độc lập có thể được scheduler cho chạy mà không cần chờ nhau.

### 22.2. Kiểm thử giới hạn concurrency

Dùng bộ đếm task đang hoạt động để xác nhận số lượng không vượt max_parallelism hoặc quota đã cấu hình.

### 22.3. Kiểm thử race condition

Chạy nhiều task cùng cập nhật dữ liệu dưới tải và xác nhận invariant. Với trạng thái chia sẻ, cần kiểm tra lock, atomic hoặc ownership theo thiết kế.

### 22.4. Kiểm thử thứ tự

Nếu DSL hứa giữ thứ tự đầu ra, tạo task có thời gian hoàn thành khác nhau và xác nhận kết quả vẫn theo thứ tự nguồn. Nếu semantics là completion order, xác nhận consumer nhận kết quả theo chính sách đó.

### 22.5. Kiểm thử cancellation

Hủy workflow khi task đang chờ I/O, đang tính toán và đang giữ resource. Xác nhận task con nhận tín hiệu phù hợp, cleanup chạy và trạng thái cuối được ghi đúng.

### 22.6. Kiểm thử lỗi đồng thời

Cho nhiều task thất bại gần nhau và kiểm tra:

- Lỗi nào được giữ lại.
- Các task còn lại có bị hủy không.
- Cleanup có hoàn tất không.
- Partial success có được báo đúng không.
- Retry có gây tác dụng phụ trùng lặp không.

### 22.7. Kiểm thử deadlock và starvation

Có thể dùng timeout kiểm thử và instrumentation để phát hiện task chờ quá lâu, lock cycle hoặc task không được scheduler cấp tài nguyên.

### 22.8. Kiểm thử tải và backpressure

Tăng tốc producer vượt khả năng consumer và xác nhận queue không tăng vô hạn, dữ liệu được xử lý theo chính sách và hệ thống phục hồi khi tải giảm.

## 23. Triển khai task concurrency bằng Java

Java cung cấp các abstraction như ExecutorService, Future, CompletableFuture, synchronized, Lock, Semaphore và các API concurrency khác. DSL có thể ánh xạ cấu trúc task sang những abstraction này.

### 23.1. ExecutorService

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

ExecutorService executor = Executors.newFixedThreadPool(4);

Future<String> orders = executor.submit(() -> loadOrders());
Future<String> customers = executor.submit(() -> loadCustomers());

String orderData = orders.get();
String customerData = customers.get();

buildReport(orderData, customerData);
executor.shutdown();
~~~

Hai task được submit trước khi caller lấy kết quả. Thread pool có tối đa bốn worker trong ví dụ. Mã minh họa cần xử lý exception, timeout và shutdown trong finally hoặc cấu trúc quản lý resource phù hợp.

### 23.2. CompletableFuture

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<Orders> orders =
    CompletableFuture.supplyAsync(this::loadOrders);

CompletableFuture<Customers> customers =
    CompletableFuture.supplyAsync(this::loadCustomers);

CompletableFuture<Report> report =
    orders.thenCombine(customers, this::buildReport);

Report result = report.join();
~~~

thenCombine kết hợp hai kết quả khi cả hai future hoàn thành. Cần chọn executor phù hợp và xử lý exceptional completion theo yêu cầu của ứng dụng.

### 23.3. Đồng bộ trạng thái

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger counter = new AtomicInteger();

Runnable work = counter::incrementAndGet;
~~~

AtomicInteger cung cấp thao tác tăng nguyên tử cho bộ đếm. Nó không thay thế lock hoặc transaction khi invariant liên quan nhiều trường.

### 23.4. Semaphore

~~~java
import java.util.concurrent.Semaphore;

Semaphore permits = new Semaphore(5);

void query() throws InterruptedException {
    permits.acquire();
    try {
        queryDatabase();
    } finally {
        permits.release();
    }
}
~~~

Ví dụ giới hạn tối đa năm lời gọi đồng thời. Việc release trong finally tránh giữ permit khi query phát sinh lỗi.

### 23.5. Mapping từ DSL

Compiler hoặc runtime có thể ánh xạ:

| Cấu trúc DSL | Abstraction Java có thể dùng |
|---|---|
| Task | Callable, Runnable hoặc CompletableFuture |
| Parallel scope | ExecutorService hoặc structured task scope |
| Await | Future.get, join hoặc API async tương ứng |
| Channel | BlockingQueue hoặc message abstraction |
| Semaphore | Semaphore |
| Atomic counter | AtomicInteger/AtomicLong |
| Lock scope | Lock với try/finally hoặc synchronized |

Đây là các lựa chọn triển khai, không phải ánh xạ bắt buộc. Semantics của DSL phải được xác định độc lập để có thể hỗ trợ backend khác.

## 24. Quy tắc thiết kế ngữ nghĩa đồng thời cho DSL

Khi định nghĩa concurrency, cần trả lời rõ các câu hỏi:

1. Một lời gọi task bắt đầu ngay hay chỉ bắt đầu khi được await?
2. Task được chạy trên thread, event loop, worker pool hay runtime phân tán?
3. Scope nào sở hữu task con?
4. Khi scope kết thúc, task con còn chạy có được phép tồn tại không?
5. Dependency có nghĩa là chờ hoàn tất, chờ thành công hay chờ dữ liệu?
6. Thứ tự kết quả được giữ hay theo thứ tự hoàn thành?
7. Mutable state có được chia sẻ giữa các task không?
8. Cơ chế đồng bộ nào được hỗ trợ?
9. Khi một task lỗi, các task khác tiếp tục, bị hủy hay được đợi?
10. Timeout và cancellation có tác động đến task nền không?
11. Có giới hạn task, thread, queue, connection và memory không?
12. Retry có yêu cầu idempotency không?
13. Tác dụng phụ và transaction được xử lý ra sao?
14. Runtime có bảo đảm deterministic execution ở phạm vi nào?
15. Diagnostics và tracing liên kết lỗi với task và source span như thế nào?

Không nên để những câu hỏi này phụ thuộc vào tình cờ của backend. Nếu hai backend thực thi cùng DSL với semantics khác nhau, chương trình có thể cho kết quả khác mà người dùng không thể dự đoán.

## 25. Những sai lầm thường gặp

### 25.1. Đồng nhất concurrency với parallelism

Một runtime có thể quản lý nhiều task trên một luồng. Ngược lại, có nhiều worker không bảo đảm workload được phân phối hiệu quả. Hãy phân biệt mô hình điều phối và việc thực thi song song thực sự.

### 25.2. Chạy mọi task không giới hạn

Khởi chạy vô hạn task có thể làm cạn thread, memory, connection hoặc quota. Cần giới hạn concurrency và queue.

### 25.3. Chia sẻ mutable state không có quy tắc

Nhiều task cùng đọc và ghi dữ liệu có thể gây race. Ưu tiên immutable data, ownership hoặc message passing; nếu cần chia sẻ, định nghĩa cơ chế đồng bộ.

### 25.4. Dùng lock quá rộng

Giữ lock trong thời gian dài hoặc khi chờ I/O làm giảm concurrency và tăng nguy cơ deadlock. Giữ vùng khóa ngắn và quy định thứ tự lấy lock.

### 25.5. Await tuần tự khi muốn chạy đồng thời

Nếu task chỉ bắt đầu tại thời điểm await, chờ từng lời gọi một sẽ tuần tự hóa công việc. Hãy khởi chạy các task độc lập trước rồi mới đợi kết quả tổng hợp.

### 25.6. Không quản lý task con

Task mồ côi có thể tiếp tục ghi dữ liệu sau khi workflow cha đã kết thúc. Structured concurrency hoặc một supervisor có vòng đời rõ giúp quản lý việc này.

### 25.7. Hủy nhưng không cleanup

Cancellation không tự giải phóng mọi resource hoặc hoàn tác side effect. Cần thiết kế cleanup, transaction hoặc compensation.

### 25.8. Giả định thứ tự hoàn thành là thứ tự đầu vào

Task nhanh có thể hoàn thành trước task được khởi chạy trước. Nếu thứ tự đầu ra quan trọng, DSL phải giữ index hoặc áp dụng ordered collection.

### 25.9. Bỏ qua backpressure

Producer nhanh hơn consumer có thể làm queue tăng vô hạn. Dùng bounded buffer và chính sách điều tiết rõ ràng.

### 25.10. Retry thao tác không idempotent

Retry một task đã gửi thanh toán hoặc tạo tài nguyên có thể lặp tác dụng phụ. Cần idempotency key, kiểm tra trạng thái hoặc compensation.

### 25.11. Không quan sát thời gian chờ

Chỉ đo thời gian thực thi không cho biết task đã chờ scheduler, lock hoặc queue bao lâu. Cần timeline và metrics cho từng giai đoạn.

### 25.12. Coi một lần test thành công là bằng chứng không có race

Interleaving hiếm có thể chỉ xuất hiện dưới tải hoặc trên môi trường khác. Kết hợp phân tích thiết kế, stress test, race detector và kiểm thử invariant.

## 26. Quy trình thiết kế và triển khai concurrency

Một quy trình thực tế:

1. **Xác định workload.** Phân biệt CPU-bound, I/O-bound, batch, streaming và workflow phân tán.
2. **Mô hình hóa task.** Xác định đơn vị công việc, input, output và vòng đời.
3. **Khai báo dependency.** Xây DAG hoặc cấu trúc phụ thuộc phù hợp; phát hiện chu trình không hợp lệ.
4. **Chọn execution model.** Thread pool, event loop, actor, task scheduler hoặc distributed worker.
5. **Đặt giới hạn.** Số task, worker, queue, connection, memory và quota.
6. **Xác định ownership.** Quy định dữ liệu nào immutable, local hoặc shared.
7. **Định nghĩa synchronization.** Chọn lock, atomic, semaphore, channel hoặc transaction khi cần.
8. **Đặc tả ordering.** Quy định thứ tự kết quả, reduction và các side effect.
9. **Thiết kế lỗi và cancellation.** Chọn fail-fast, collect-errors, partial success, timeout và cleanup.
10. **Thêm backpressure.** Kiểm soát tốc độ dữ liệu và kích thước buffer.
11. **Bổ sung observability.** Task ID, timeline, trace context và metrics.
12. **Kiểm thử concurrency.** Bao phủ dependency, race, ordering, cancellation, lỗi, deadlock và tải.
13. **Xác nhận semantics giữa backend.** Bảo đảm các backend thực hiện cùng hợp đồng đồng thời của DSL.

Chỉ nên đưa vào DSL những abstraction người dùng miền thực sự cần. Một ngôn ngữ workflow có thể chỉ cần task, dependency và parallel scope; DSL hướng đến lập trình hệ thống có thể cần thêm channel, lock hoặc atomic operation.

## 27. Câu hỏi tự kiểm tra

1. Phân biệt concurrency và parallelism bằng ví dụ.
2. Nêu các mô hình thực thi đồng thời phổ biến và tình huống phù hợp của từng mô hình.
3. Task-based concurrency khác thread-based concurrency như thế nào?
4. Dependency graph và DAG giúp scheduler xác định task sẵn sàng ra sao?
5. Race condition và data race khác nhau như thế nào?
6. Vì sao immutable data và ownership có thể giảm lỗi đồng thời?
7. Phân biệt mutex, semaphore, atomic operation, barrier và channel.
8. Deadlock, livelock và starvation là gì?
9. Happens-before liên quan thế nào đến visibility?
10. Ordered result khác completion order ra sao?
11. Future, Promise, async và await hỗ trợ tổ chức công việc bất đồng bộ như thế nào?
12. Structured concurrency quản lý task con và cancellation ra sao?
13. Khi một task trong parallel scope thất bại, DSL có thể áp dụng những chính sách nào?
14. Backpressure giải quyết vấn đề gì trong pipeline streaming?
15. Vì sao timeout hoặc cancellation không đồng nghĩa side effect đã được hoàn tác?
16. Điều kiện nào giúp parallel reduction có kết quả đúng và có thể tái lập?
17. Hãy đề xuất mô hình concurrency cho workflow đọc ba nguồn độc lập, hợp nhất dữ liệu và ghi báo cáo; nêu dependency, giới hạn tài nguyên và chính sách lỗi.
