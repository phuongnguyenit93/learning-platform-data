# MPI, giao tiếp giữa node và yêu cầu độ trễ mạng

Điện toán hiệu năng cao (HPC) thường chia một bài toán lớn thành nhiều phần để chạy đồng thời trên nhiều CPU hoặc nhiều node. Khi các phần dữ liệu nằm trong bộ nhớ của những node khác nhau, tiến trình phải trao đổi dữ liệu qua mạng. Thời gian giao tiếp có thể nhỏ hơn nhiều so với thời gian tính toán ở một bước, nhưng khi số lần trao đổi tăng hoặc bài toán được chia quá nhỏ, độ trễ mạng có thể trở thành nút thắt chính.

Message Passing Interface (MPI) là chuẩn giao tiếp phổ biến cho ứng dụng song song phân tán. MPI cung cấp các thao tác gửi/nhận dữ liệu giữa tiến trình, đồng bộ và phép toán tập thể trên một nhóm tiến trình. Hiệu năng MPI phụ thuộc vào cách chương trình tổ chức giao tiếp, số lượng message, kích thước message, topology node, vị trí rank, băng thông và độ trễ của interconnect. Khi triển khai HPC trên cloud, cần chọn loại máy, placement và mạng phù hợp với pattern giao tiếp của ứng dụng.

Bài học này giải thích cách MPI hoạt động, vì sao latency quan trọng, cách ước lượng chi phí giao tiếp, lựa chọn mạng giữa node, đo benchmark và tối ưu một workload phân tán.

## 1. Vì sao HPC cần giao tiếp giữa node?

Một node thường có nhiều core CPU và có thể chạy nhiều tiến trình hoặc thread. Nếu toàn bộ dữ liệu và tính toán vừa trong một node, ứng dụng có thể dùng shared memory để trao đổi dữ liệu nhanh. Khi bài toán vượt khả năng CPU hoặc memory của một node, workload được phân phối sang nhiều node.

Mỗi node có bộ nhớ riêng. Một tiến trình trên node A không thể đọc trực tiếp vùng nhớ của tiến trình trên node B như truy cập RAM cục bộ. Chúng cần gửi dữ liệu qua interconnect bằng MPI hoặc một cơ chế giao tiếp khác.

Các ví dụ:

- Mô phỏng thời tiết chia lưới không gian thành nhiều miền; mỗi node tính một miền và trao đổi giá trị ở biên.
- Mô phỏng động lực học chất lưu cần trao đổi dữ liệu giữa các ô lưới lân cận ở mỗi bước thời gian.
- Mô phỏng phân tử phân chia hạt và lực tương tác giữa các miền.
- Đại số tuyến tính phân tán cần trao đổi block ma trận và thực hiện phép toán collective.
- Huấn luyện mô hình phân tán cần đồng bộ gradient giữa các worker.
- Mô phỏng vật liệu hoặc kết cấu chia miền tính toán cho nhiều node.

Tăng số node có thể tăng tổng năng lực tính toán, nhưng cũng tăng lượng giao tiếp. Nếu mỗi bước tính toán cần nhiều trao đổi ngắn, latency có thể chi phối tổng thời gian dù băng thông danh nghĩa rất cao.

## 2. MPI là gì?

MPI là một chuẩn định nghĩa API và ngữ nghĩa cho giao tiếp giữa các tiến trình trong ứng dụng song song. MPI không phải một network protocol duy nhất và cũng không phải một scheduler. Các implementation như Open MPI, MPICH và Intel MPI cung cấp thư viện runtime để ánh xạ lệnh MPI lên shared memory, TCP/IP, RDMA hoặc transport phù hợp với hệ thống.

Một chương trình MPI thường có nhiều process. Mỗi process có địa chỉ bộ nhớ riêng và được định danh bằng một rank trong communicator.

Các khái niệm chính:

| Khái niệm | Ý nghĩa |
|---|---|
| Process | Tiến trình chạy một bản chương trình MPI |
| Rank | Số định danh của process trong communicator |
| Communicator | Nhóm process được phép giao tiếp với nhau và có không gian rank riêng |
| MPI_COMM_WORLD | Communicator mặc định chứa các process được khởi chạy trong job |
| Point-to-point | Gửi dữ liệu từ một rank tới một rank khác |
| Collective | Thao tác phối hợp giữa các rank trong communicator |
| Message tag | Giá trị dùng phân biệt loại message trong point-to-point |
| Datatype | Mô tả kiểu và bố cục dữ liệu được gửi/nhận |
| Request | Handle theo dõi thao tác giao tiếp không blocking |
| MPI implementation | Thư viện thực thi MPI và kết nối tới transport/hardware |

Một communicator giúp tách các nhóm tiến trình theo miền dữ liệu hoặc chức năng. Ví dụ, một chương trình có thể tạo communicator riêng cho nhóm rank xử lý từng vùng lưới hoặc từng tầng của thuật toán.

## 3. Vòng đời cơ bản của chương trình MPI

Một chương trình MPI thường thực hiện các bước:

1. Khởi tạo môi trường MPI.
2. Lấy rank và tổng số process.
3. Phân chia dữ liệu và công việc theo rank.
4. Thực hiện tính toán cục bộ.
5. Gửi/nhận dữ liệu hoặc gọi collective khi cần.
6. Tổng hợp kết quả.
7. Giải phóng tài nguyên và kết thúc MPI.

Ví dụ C tối giản:

~~~c
#include <mpi.h>
#include <stdio.h>

int main(int argc, char **argv) {
    int rank = 0;
    int size = 0;

    MPI_Init(&argc, &argv);
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &size);

    printf("Hello from rank %d of %d\n", rank, size);

    MPI_Finalize();
    return 0;
}
~~~

Biên dịch và chạy ví dụ trên một môi trường có MPI:

~~~bash
mpicc hello.c -o hello
mpirun -np 4 ./hello
~~~

Thứ tự dòng output có thể thay đổi vì các process chạy đồng thời. Lệnh mpirun là ví dụ thường gặp; trên cluster dùng Slurm có thể chạy bằng srun với plugin MPI phù hợp. Cần dùng đúng launcher, MPI library và runtime được cài trên cluster.

## 4. Point-to-point communication

Point-to-point là giao tiếp giữa một rank gửi và một rank nhận. Hai API cơ bản là MPI_Send và MPI_Recv.

Ví dụ rank 0 gửi một số nguyên cho rank 1:

~~~c
int value = 42;

if (rank == 0) {
    MPI_Send(&value, 1, MPI_INT, 1, 100, MPI_COMM_WORLD);
} else if (rank == 1) {
    MPI_Recv(&value, 1, MPI_INT, 0, 100,
             MPI_COMM_WORLD, MPI_STATUS_IGNORE);
}
~~~

Các tham số quan trọng gồm buffer, số phần tử, datatype, rank đích/nguồn, tag và communicator. Hai phía phải thống nhất về communicator, source/destination, tag và kiểu dữ liệu tương thích.

### 4.1. Blocking và nonblocking

Blocking operation có thể chờ cho tới khi thao tác đạt điều kiện hoàn tất theo ngữ nghĩa MPI. MPI_Send không nhất thiết luôn chờ receiver đọc xong dữ liệu; implementation có thể buffer message nhỏ hoặc dùng rendezvous protocol với message lớn. Không nên dựa vào một giả định cụ thể về buffering để thiết kế chương trình.

Nonblocking API gồm MPI_Isend và MPI_Irecv. Chúng khởi tạo thao tác rồi trả về request để chương trình có thể thực hiện công việc khác trước khi chờ hoàn tất.

~~~c
MPI_Request req[2];

MPI_Irecv(recv_buf, count, MPI_DOUBLE, peer, 7,
          MPI_COMM_WORLD, &req[0]);
MPI_Isend(send_buf, count, MPI_DOUBLE, peer, 7,
          MPI_COMM_WORLD, &req[1]);

/* Có thể tính toán độc lập trong lúc truyền dữ liệu. */

MPI_Waitall(2, req, MPI_STATUSES_IGNORE);
~~~

Buffer của thao tác nonblocking phải còn hợp lệ và không được đọc/ghi sai cách trước khi request hoàn tất. MPI_Wait, MPI_Test hoặc các hàm tương ứng được dùng để xác định completion.

### 4.2. Overlap giao tiếp và tính toán

Nonblocking communication chỉ tạo cơ hội overlap; nó không bảo đảm mạng và CPU tự động tiến triển song song. Mức overlap phụ thuộc MPI implementation, NIC, progress engine, cấu hình runtime và cấu trúc chương trình.

Để overlap có ích:

- Khởi tạo receive sớm để rank có thể nhận dữ liệu.
- Gửi dữ liệu ngay khi buffer đã sẵn sàng.
- Thực hiện phần tính toán không phụ thuộc message.
- Chờ completion ngay trước khi cần dữ liệu nhận.
- Tránh ghi vào send buffer trước khi send hoàn tất.
- Đo thực tế xem thời gian giao tiếp có được che khuất bởi tính toán hay không.

Nếu chương trình gọi MPI_Waitall ngay sau MPI_Isend/MPI_Irecv mà không có công việc độc lập ở giữa, lợi ích overlap có thể rất nhỏ.

## 5. Collective communication

Collective operation phối hợp nhiều rank trong một communicator. Các thao tác thường gặp:

| Hàm | Mục đích |
|---|---|
| MPI_Bcast | Một rank phát dữ liệu tới tất cả rank |
| MPI_Reduce | Kết hợp dữ liệu từ nhiều rank và trả kết quả về root |
| MPI_Allreduce | Kết hợp dữ liệu và phân phối kết quả cho mọi rank |
| MPI_Gather | Thu thập dữ liệu từ các rank về root |
| MPI_Allgather | Thu thập và phân phối dữ liệu cho mọi rank |
| MPI_Scatter | Root chia dữ liệu cho các rank |
| MPI_Alltoall | Mỗi rank trao đổi block dữ liệu với mọi rank |
| MPI_Barrier | Đồng bộ: các rank trong communicator cùng đi qua điểm barrier |

Ví dụ tổng hợp tổng cục bộ trên tất cả rank:

~~~c
double local_sum = compute_local_sum();
double global_sum = 0.0;

MPI_Allreduce(&local_sum, &global_sum, 1, MPI_DOUBLE,
              MPI_SUM, MPI_COMM_WORLD);
~~~

MPI_Allreduce có thể là phần quan trọng trong mỗi iteration của thuật toán. Nếu gọi nhiều lần với message nhỏ, latency và synchronization có thể chi phối thời gian. Có thể giảm số collective bằng cách gộp scalar, dùng thuật toán communication-avoiding hoặc thay đổi tần suất đồng bộ nếu tính đúng đắn cho phép.

Tất cả rank trong communicator cần gọi collective theo thứ tự tương thích. Nếu một rank bỏ qua collective hoặc gọi theo thứ tự khác, chương trình có thể treo hoặc có hành vi không hợp lệ.

## 6. Độ trễ và băng thông là hai yếu tố khác nhau

Latency là thời gian cần để một thao tác hoặc message bắt đầu/hoàn tất theo phép đo cụ thể. Bandwidth là lượng dữ liệu có thể truyền trong một đơn vị thời gian sau khi đường truyền hoạt động.

- Message nhỏ thường nhạy với latency.
- Message lớn thường nhạy với bandwidth.
- Nhiều message nhỏ có thể tốn hơn một message lớn có cùng tổng byte.
- Collective có thể chịu thêm chi phí đồng bộ và thuật toán trao đổi giữa nhiều rank.

Độ trễ thấp đặc biệt quan trọng với ứng dụng có nhiều vòng trao đổi ngắn, ví dụ halo exchange mỗi bước mô phỏng hoặc collective đồng bộ gradient. Băng thông cao quan trọng với truyền block dữ liệu lớn, checkpoint hoặc all-to-all dữ liệu lớn.

### 6.1. Mô hình latency-bandwidth đơn giản

Một mô hình thường dùng để ước lượng thời gian truyền một message có kích thước n byte:

\[
T_{message} \approx \alpha + \frac{n}{\beta}
\]

Trong đó:

- \(\alpha\) là chi phí cố định/latency của thao tác.
- \(n\) là kích thước message.
- \(\beta\) là băng thông hiệu dụng.

Mô hình này còn gọi là alpha-beta hoặc latency-bandwidth model. Nó là xấp xỉ; thời gian thực tế còn phụ thuộc protocol, copy memory, queueing, topology, congestion, NIC và MPI implementation.

Với message rất nhỏ, thành phần alpha chiếm phần lớn. Với message lớn, n/beta trở nên đáng kể. Vì vậy, tăng bandwidth danh nghĩa không nhất thiết cải thiện nhiều ứng dụng gửi hàng nghìn message nhỏ.

### 6.2. Nhiều message nhỏ và gộp message

Giả sử cần gửi tổng cộng 1 MB:

- Một message 1 MB có một lần chi phí latency.
- 1.000 message 1 KB có thể chịu 1.000 lần chi phí khởi tạo message.

Nếu latency mỗi message là 5 microsecond, phần chi phí cố định lý tưởng cho 1.000 message có thể xấp xỉ 5 ms, chưa tính truyền dữ liệu và xử lý. Con số chỉ minh họa tác động của số lần gửi.

Có thể giảm overhead bằng cách gộp dữ liệu thành message lớn hơn, nhưng việc gộp cũng có thể làm tăng thời gian chờ để đủ batch và memory buffer. Chọn batch size dựa trên latency budget và pattern của thuật toán.

## 7. Vì sao latency mạng ảnh hưởng mạnh tới scaling?

Scaling của ứng dụng song song thường được xem theo hai mô hình:

- **Strong scaling:** giữ nguyên kích thước bài toán và tăng số process. Mỗi process làm ít việc hơn, nhưng tỷ lệ giao tiếp/synchronization thường tăng.
- **Weak scaling:** tăng kích thước bài toán theo số process để giữ khối lượng công việc trên mỗi process gần như không đổi.

Strong scaling thường đạt giới hạn khi thời gian tính toán giảm nhưng chi phí giao tiếp, đồng bộ và imbalance không giảm tương ứng.

Một mô hình thời gian tổng quát:

\[
T_{total} =
T_{compute} + T_{communication} + T_{synchronization}
+ T_{imbalance}
\]

Các thành phần có thể chồng lấp nếu ứng dụng dùng nonblocking communication hiệu quả, do đó đây là mô hình phân tích chứ không phải lúc nào cũng cộng trực tiếp được mọi thời gian.

Nếu tăng số node khiến mỗi rank xử lý một miền dữ liệu nhỏ hơn, số byte trao đổi có thể giảm, nhưng số message hoặc số neighbor có thể tăng. Ở một mức nào đó, chi phí mạng và đồng bộ lấn át lợi ích thêm CPU.

### 7.1. Tỷ lệ computation/communication

Một ứng dụng hiệu quả thường có đủ computation độc lập giữa các lần trao đổi. Nếu mỗi 100 microsecond tính toán phải chờ 200 microsecond mạng, tăng thêm node có thể không giúp.

Có thể theo dõi:

- Thời gian compute cục bộ.
- Thời gian chờ MPI.
- Số message gửi/nhận mỗi iteration.
- Byte gửi/nhận mỗi rank.
- Tỷ lệ thời gian trong collective.
- Rank chậm nhất và độ lệch giữa các rank.

MPI profiling hoặc trace giúp xác định function nào giao tiếp nhiều, message size nào phổ biến và rank nào thường chờ.

## 8. Halo exchange: ví dụ giao tiếp giữa node

Trong mô phỏng lưới, mỗi rank thường sở hữu một miền con và cần giá trị ở biên từ các miền lân cận. Những vùng dữ liệu biên được gọi là halo hoặc ghost cells.

~~~mermaid
flowchart LR
    A[Rank 0] <-->|Halo data| B[Rank 1]
    B <-->|Halo data| C[Rank 2]
    C <-->|Halo data| D[Rank 3]
~~~

Mỗi iteration:

1. Rank tính các cell bên trong không phụ thuộc dữ liệu mới.
2. Rank gửi biên của miền cho neighbor.
3. Rank nhận halo từ neighbor.
4. Rank tính cell ở biên cần halo.
5. Chuyển sang iteration tiếp theo.

Nếu dùng blocking send/receive sai thứ tự, các rank có thể chờ nhau và deadlock. MPI_Sendrecv cung cấp cách phối hợp send và receive trong một lời gọi, hữu ích cho pattern trao đổi hai chiều.

Ví dụ vòng lưới tuần hoàn một chiều:

~~~c
double send_left = left_boundary_value;
double send_right = right_boundary_value;
double recv_left = 0.0;
double recv_right = 0.0;

int left = (rank - 1 + size) % size;
int right = (rank + 1) % size;

/* Gửi biên trái sang rank trái, nhận biên phải từ rank phải. */
MPI_Sendrecv(&send_left, 1, MPI_DOUBLE, left, 10,
             &recv_right, 1, MPI_DOUBLE, right, 10,
             MPI_COMM_WORLD, MPI_STATUS_IGNORE);

/* Gửi biên phải sang rank phải, nhận biên trái từ rank trái. */
MPI_Sendrecv(&send_right, 1, MPI_DOUBLE, right, 11,
             &recv_left, 1, MPI_DOUBLE, left, 11,
             MPI_COMM_WORLD, MPI_STATUS_IGNORE);
~~~

Ví dụ giả định mỗi rank có hai neighbor trong topology vòng. Với miền không tuần hoàn, dùng MPI_PROC_NULL cho biên ngoài hoặc communicator/topology phù hợp. Với lưới 2D/3D, mỗi rank có thể trao đổi với nhiều neighbor; cần xác định hướng, tag và thứ tự dữ liệu nhất quán.

## 9. Topology node và vị trí rank

Không phải mọi giao tiếp đều đi qua mạng vật lý. Hai rank trên cùng node có thể dùng shared memory transport; rank ở hai node khác nhau phải đi qua NIC và interconnect.

Topology ảnh hưởng hiệu năng:

- Số socket CPU và NUMA domain.
- Vị trí memory controller.
- Số core trên mỗi socket.
- Vị trí NIC gắn với PCIe/NUMA.
- Băng thông và số lane của interconnect.
- Cách rank được pin vào core.
- Số process trên mỗi node.
- Việc oversubscribe core hoặc memory bandwidth.

Nếu rank chạy trên NUMA node xa NIC hoặc memory của nó, dữ liệu có thể đi qua inter-socket link trước khi tới NIC. Điều này tăng latency và tiêu thụ băng thông nội bộ.

### 9.1. Rank binding và process placement

Rank binding gắn process vào core hoặc tập core cụ thể. Placement quyết định rank nào chạy trên node, socket hoặc NUMA domain nào.

Nguyên tắc thực tế:

- Tránh nhiều rank tranh cùng core nếu workload không chủ đích oversubscribe.
- Xem số rank phù hợp với core vật lý và SMT.
- Giữ rank và memory gần NIC/NUMA khi giao tiếp mạng nặng.
- Dùng topology-aware mapping nếu thuật toán có neighbor communication.
- Đo nhiều cách mapping vì best placement phụ thuộc workload và phần cứng.

Ví dụ tùy chọn của Open MPI:

~~~bash
mpirun -np 16 --map-by ppr:8:node --bind-to core ./solver
~~~

Lệnh trên là ví dụ cho Open MPI và giả định hai node có đủ core phù hợp. Tùy chọn launcher khác nhau giữa Open MPI, MPICH, Intel MPI và Slurm. Kiểm tra help của launcher và cấu hình scheduler trước khi dùng trong cluster.

## 10. Interconnect cho HPC

Interconnect là hệ thống kết nối các node và NIC. Các loại phổ biến:

| Công nghệ | Đặc điểm khái quát | Điểm cần cân nhắc |
|---|---|---|
| Ethernet TCP/IP | Phổ biến, dễ tích hợp, có nhiều mức tốc độ | Latency, CPU overhead, congestion và cấu hình mạng |
| High-speed Ethernet | Tăng băng thông và có thể giảm latency so với mạng phổ thông | NIC, switch, oversubscription và transport stack |
| RoCE | RDMA over Converged Ethernet, cho phép RDMA trên Ethernet | Cần cấu hình loss/congestion control và hạ tầng tương thích |
| InfiniBand | Interconnect HPC với RDMA và các cơ chế transport chuyên dụng | Chi phí, khả năng cung cấp và topology |
| Shared memory | Giao tiếp giữa process cùng node | NUMA, copy overhead, memory bandwidth |

Không thể chỉ nhìn tốc độ link để kết luận hiệu năng. Một mạng 100 Gb/s có thể kém hơn kỳ vọng nếu switch oversubscribed, NIC bị chia sẻ, CPU xử lý protocol quá tải hoặc traffic đi qua nhiều hop.

### 10.1. TCP/IP và socket transport

MPI implementation có thể dùng TCP/IP qua Ethernet. Đây là lựa chọn tương thích rộng và dễ triển khai. Tuy nhiên, CPU phải xử lý stack network, packet processing và copy dữ liệu theo đường đi của implementation. Với workload nhạy latency hoặc message rate cao, overhead này có thể đáng kể.

Tối ưu TCP/IP có thể gồm:

- Chọn NIC và instance có network bandwidth phù hợp.
- Tránh oversubscription ở switch hoặc host.
- Dùng MTU phù hợp và nhất quán trên đường đi.
- Theo dõi retransmission, packet drop và congestion.
- Cấu hình MPI transport để dùng đúng interface.
- Dùng connection và process placement phù hợp.

Jumbo frame chỉ hữu ích khi toàn bộ đường đi hỗ trợ MTU tương ứng và được cấu hình đồng nhất. MTU mismatch có thể gây fragmentation hoặc black-hole path MTU.

### 10.2. RDMA là gì?

Remote Direct Memory Access (RDMA) cho phép NIC truyền dữ liệu giữa memory region của các host với ít can thiệp của CPU hơn so với đường socket truyền thống. Một số transport RDMA hỗ trợ thao tác one-sided như read/write, bên cạnh send/receive.

Lợi ích có thể gồm:

- Giảm CPU overhead cho data movement.
- Giảm latency cho message phù hợp.
- Tăng throughput khi truyền dữ liệu lớn.
- Hỗ trợ overlap communication/computation tốt hơn trong một số workload.

RDMA không làm mọi message tự động nhanh. Setup queue pair, memory registration, synchronization, message size và transport selection vẫn có overhead. Ứng dụng hoặc MPI implementation phải hỗ trợ đúng transport và cấu hình. Nếu workload bị giới hạn bởi thuật toán hoặc collective synchronization, RDMA có thể không cải thiện nhiều.

### 10.3. RoCE và InfiniBand

RoCE triển khai RDMA trên Ethernet. Hiệu năng phụ thuộc NIC, switch, congestion control và cấu hình loss behavior. RoCE v2 sử dụng UDP/IP encapsulation để có thể định tuyến ở lớp IP, nhưng hạ tầng vẫn cần được thiết kế phù hợp với traffic RDMA.

InfiniBand là interconnect chuyên dụng thường gặp trong cluster HPC. Nó cung cấp transport và cơ chế RDMA được thiết kế cho giao tiếp hiệu năng cao. Khi chọn cluster, cần kiểm tra NIC, switch fabric, driver, firmware, MPI stack và khả năng hỗ trợ của cloud provider.

## 11. Mạng HPC trên cloud

Cloud HPC cần đồng thời xem xét compute instance, network fabric và cách đặt node. Một số nền tảng cung cấp instance có NIC hiệu năng cao hoặc network adapter hỗ trợ RDMA; một số cung cấp placement group/cluster placement để đặt các node gần nhau hơn trong hạ tầng.

Các câu hỏi khi chọn môi trường:

- Instance family có hỗ trợ network adapter cần thiết không?
- Băng thông mạng được công bố là tối đa hay bảo đảm?
- Bandwidth có phụ thuộc kích thước instance hoặc số flow không?
- Các instance có thể nằm cùng cluster placement group hoặc placement policy không?
- RDMA có được hỗ trợ trong region và zone cần dùng không?
- MPI implementation có tương thích với driver và transport không?
- Có giới hạn traffic giữa zone hoặc giữa subnet không?
- Security group, firewall và routing có cho phép các port MPI cần thiết không?
- Có thể dùng node đồng nhất về CPU, NIC và firmware không?
- Chi phí truyền dữ liệu hoặc dịch vụ mạng có ảnh hưởng tổng chi phí không?

Không phải mọi loại VM đều có cùng network performance. Instance compute-optimized có thể có CPU mạnh nhưng NIC không phù hợp với communication-heavy workload. Cần chọn theo profile giao tiếp chứ không chỉ theo số vCPU.

### 11.1. Placement và failure domain

Đặt node gần nhau có thể giảm số hop hoặc tăng cơ hội dùng fabric hiệu năng cao, nhưng placement group không thay thế thiết kế HA. HPC job thường cần một nhóm node đồng nhất trong cùng cluster; nếu một node mất, job MPI truyền thống có thể thất bại toàn bộ trừ khi ứng dụng có checkpoint/restart.

Một job cần latency thấp có thể ưu tiên node trong cùng placement domain và cùng network fabric. Một hệ thống cần chịu lỗi vùng địa lý lại có mục tiêu khác. Không nên phân tán các rank của một job latency-sensitive qua nhiều region vì latency WAN thường lớn hơn nhiều so với interconnect nội vùng.

## 12. Message size, protocol và ngưỡng eager/rendezvous

MPI implementation có thể dùng các protocol khác nhau theo message size:

- **Eager protocol:** thường phù hợp message nhỏ; sender có thể gửi trước khi receiver đăng ký receive, dựa vào buffer nội bộ.
- **Rendezvous protocol:** thường dùng cho message lớn; hai phía phối hợp trước khi truyền payload để tránh buffering lớn.

Ngưỡng chuyển protocol phụ thuộc implementation và transport. Khi message size quanh ngưỡng, latency có thể thay đổi. Không nên giả định một ngưỡng cố định cho mọi MPI library.

Hãy đo latency theo nhiều message size thay vì chỉ đo một kích thước. Nếu workload gửi nhiều message gần ngưỡng, thay đổi aggregation hoặc buffer size có thể ảnh hưởng rõ rệt.

## 13. Collective communication và độ trễ

Collective operation có thể dùng các thuật toán khác nhau:

- Tree-based reduction/broadcast.
- Ring allreduce.
- Recursive doubling.
- Reduce-scatter kết hợp allgather.
- Hierarchical collective theo node rồi liên node.
- Topology-aware collective.

Lựa chọn phụ thuộc số rank, message size, topology và MPI implementation. Một thuật toán giảm số vòng latency có thể tốt với message nhỏ; thuật toán ring có thể đạt băng thông tốt với message lớn. Hierarchical collective có thể tận dụng shared memory trong node và interconnect giữa node.

Không nên ép một thuật toán collective cho mọi workload nếu implementation đã có tuning phù hợp. Benchmark với số rank và message size thực tế, đồng thời xem phiên bản MPI và cấu hình transport.

### 13.1. Allreduce trong vòng lặp solver

Nhiều solver lặp dùng MPI_Allreduce để tính norm, residual hoặc điều kiện dừng. Nếu mỗi iteration có một collective latency-sensitive, thời gian tổng có thể bị giới hạn bởi latency và số vòng đồng bộ.

Các hướng tối ưu:

- Gộp nhiều scalar vào một collective nếu đúng thuật toán.
- Giảm số lần kiểm tra điều kiện dừng nhưng vẫn bảo đảm hội tụ.
- Dùng thuật toán communication-avoiding hoặc pipelined nếu phù hợp.
- Dùng nonblocking collective như MPI_Iallreduce để overlap phần tính toán độc lập.
- Giảm số rank nếu communication cost vượt lợi ích compute.
- Chọn topology-aware collective phù hợp.

Nonblocking collective yêu cầu mọi rank gọi thao tác tương ứng theo đúng thứ tự và tuân thủ quy tắc buffer. Việc overlap vẫn phụ thuộc progress của MPI implementation.

## 14. Latency, jitter và tail behavior

Đối với HPC, latency trung bình chưa đủ. Sự biến động giữa các lần trao đổi có thể khiến một rank chậm làm cả communicator phải chờ.

Jitter là mức biến động latency. Tail latency (ví dụ p95 hoặc p99) cho biết các lần giao tiếp chậm ở phần đuôi phân bố.

Nguồn gây jitter:

- Network congestion và queueing.
- Switch buffer pressure hoặc oversubscription.
- Packet loss/retransmission với transport tương ứng.
- CPU scheduling và noisy neighbor.
- NIC interrupt/processing contention.
- NUMA remote access.
- Process không được pin hoặc oversubscribe core.
- Background traffic, storage I/O hoặc telemetry.
- Khác biệt cấu hình giữa node.

Một collective thường hoàn tất khi rank chậm nhất hoàn thành phần việc cần thiết. Vì vậy, một node có latency xấu hoặc CPU contention có thể kéo dài toàn bộ iteration dù các node khác đã xong.

## 15. Ước lượng ngân sách latency cho ứng dụng

Hãy phân rã một iteration thành compute, point-to-point, collective và synchronization.

Ví dụ minh họa:

| Thành phần mỗi iteration | Thời gian |
|---|---:|
| Tính toán cục bộ | 2,0 ms |
| Halo exchange với neighbor | 0,15 ms |
| Allreduce | 0,10 ms |
| Chờ imbalance/synchronization | 0,25 ms |
| Tổng gần đúng | 2,50 ms |

Nếu halo exchange tăng lên 0,8 ms do network latency hoặc nhiều message nhỏ, tổng thời gian tăng đáng kể. Nếu tăng số node làm compute giảm từ 2,0 ms xuống 1,0 ms nhưng communication tăng lên 1,1 ms, speedup có thể thấp hơn mong đợi.

Các con số chỉ là minh họa. Trong ứng dụng có overlap, cần đo timeline để xác định phần giao tiếp nào bị che khuất bởi computation và phần nào nằm trên critical path.

## 16. Đo hiệu năng mạng và MPI

Nên đo cả microbenchmark lẫn ứng dụng thực tế.

### 16.1. Ping-pong latency

Hai rank gửi message qua lại để đo thời gian round trip. Nếu đo round trip T_RTT, latency một chiều thường được ước lượng gần bằng T_RTT/2 trong điều kiện đối xứng, nhưng đây là giả định cần nêu rõ. Dùng nhiều message size và lặp nhiều lần.

### 16.2. Bandwidth test

Gửi message lớn hoặc stream nhiều message để đo throughput. Cần đo theo kích thước buffer, số rank và số flow dự kiến. Throughput một cặp rank không nhất thiết phản ánh aggregate bandwidth khi toàn cluster cùng giao tiếp.

### 16.3. Collective benchmark

Đo thời gian MPI_Bcast, MPI_Allreduce, MPI_Alltoall và các collective mà ứng dụng sử dụng. Chạy ở số rank tương tự production, với message size tương tự.

### 16.4. Công cụ benchmark

Các bộ benchmark thường gặp gồm OSU Micro-Benchmarks và Intel MPI Benchmarks (IMB), cùng công cụ profiling/tracing tương thích MPI. Tên binary và tùy chọn phụ thuộc gói cài đặt. Kiểm tra tài liệu của bản cài thay vì giả định mọi cluster có cùng lệnh.

Một quy trình benchmark:

1. Xác minh MPI runtime, NIC và transport được chọn đúng.
2. Chạy hai rank cùng node để có baseline intra-node.
3. Chạy hai rank khác node để đo inter-node.
4. Chạy nhiều cặp rank đồng thời để quan sát contention.
5. Đo nhiều message size từ nhỏ tới lớn.
6. Đo collective ở nhiều số rank.
7. Lặp lại nhiều lần và báo cáo median, p95/p99 hoặc độ biến động.
8. Chạy ứng dụng thực tế và đối chiếu với microbenchmark.
9. Ghi node type, placement, rank mapping, MPI version và network configuration.

Không chạy benchmark đồng thời với workload khác trên cùng node nếu mục tiêu là đo baseline sạch. Nếu muốn đo môi trường chia sẻ production, hãy ghi rõ điều kiện contention.

## 17. Đo thời gian trong chương trình MPI

Có thể dùng MPI_Wtime() để đo thời gian cục bộ. Khi tổng hợp thời gian giữa rank, cần chú ý đồng hồ trên các node có thể không đồng bộ hoàn toàn. Cách phổ biến là đo elapsed time mỗi rank trong cùng vùng mã và dùng MPI_Reduce/MPI_Allreduce lấy giá trị lớn nhất, vì thời gian hoàn tất job thường bị chi phối bởi rank chậm nhất.

Ví dụ:

~~~c
double t0 = MPI_Wtime();

/* Vùng tính toán và giao tiếp cần đo. */

double local_elapsed = MPI_Wtime() - t0;
double max_elapsed = 0.0;

MPI_Reduce(&local_elapsed, &max_elapsed, 1, MPI_DOUBLE,
           MPI_MAX, 0, MPI_COMM_WORLD);

if (rank == 0) {
    printf("Maximum rank elapsed: %.6f seconds\n", max_elapsed);
}
~~~

Không cần thêm MPI_Barrier trước mọi phép đo một cách máy móc. Barrier cũng là một collective có chi phí và có thể thay đổi trạng thái đồng bộ của workload. Nếu cần căn chỉnh điểm bắt đầu, hãy nêu rõ barrier là một phần của benchmark hay chỉ dùng để đồng bộ trước vùng đo.

## 18. Tối ưu giao tiếp MPI

Các hướng tối ưu cần dựa trên profile:

### 18.1. Giảm số message

- Gộp nhiều message nhỏ có cùng đích thành một message.
- Dùng datatype hoặc packing phù hợp.
- Giảm số lần trao đổi trong mỗi iteration.
- Tái sử dụng buffer khi an toàn.
- Tránh gửi dữ liệu không cần thiết hoặc gửi lại dữ liệu đã có.

### 18.2. Giảm lượng dữ liệu

- Phân vùng dữ liệu để giảm biên cần trao đổi.
- Dùng compression nếu CPU cost nhỏ hơn lợi ích network.
- Chỉ gửi phần dữ liệu thay đổi.
- Dùng precision phù hợp với yêu cầu khoa học.
- Tái cấu trúc thuật toán để giảm communication volume.

Compression không phải lúc nào cũng tốt: nếu CPU đã bão hòa hoặc message nhỏ, chi phí nén/giải nén có thể lớn hơn thời gian mạng tiết kiệm được.

### 18.3. Overlap computation và communication

Dùng nonblocking point-to-point hoặc collective để truyền dữ liệu trong lúc tính phần độc lập. Kiểm tra progress behavior và không sử dụng buffer trước completion.

### 18.4. Tối ưu placement và rank mapping

Đặt rank giao tiếp nhiều ở vị trí gần nhau theo topology; cân nhắc node-local shared memory và NUMA. Đo nhiều mapping để tránh giả định một cấu hình phù hợp mọi thuật toán.

### 18.5. Chọn số node hợp lý

Tăng node chỉ khi phần compute giảm nhiều hơn chi phí giao tiếp. Với strong scaling, tìm điểm mà thêm node không còn cải thiện throughput hoặc thời gian hoàn thành.

## 19. Troubleshooting giao tiếp MPI

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Job treo tại send/receive | Deadlock, tag/source mismatch, rank không tới điểm nhận | Kiểm tra call order, communicator, tag và trace |
| Chạy tốt một node nhưng chậm nhiều node | Interconnect, transport hoặc placement | Xác minh NIC, transport và inter-node benchmark |
| Latency tăng khi thêm rank | Congestion, collective overhead, oversubscription | Đo theo rank count, network và CPU |
| Một vài rank chậm hơn nhiều | Load imbalance, NUMA, noisy neighbor | So thời gian từng rank và mapping |
| MPI không dùng RDMA | Library/driver mismatch, transport không được chọn | Kiểm tra MPI diagnostics, provider và NIC |
| Message lớn chậm bất thường | Bandwidth, protocol threshold, memory copy | Đo bandwidth theo message size |
| Thỉnh thoảng timeout | Jitter, packet loss, congestion hoặc node issue | Theo dõi tail latency, NIC/switch counters và system logs |
| Chỉ lỗi trong cloud | Security rule, routing, interface hoặc placement | Kiểm tra network policy, port, route và adapter |

Đối với job MPI truyền thống, một process bị lỗi thường khiến toàn job thất bại. Cần có checkpoint/restart hoặc cơ chế fault tolerance phù hợp nếu workload cần tiếp tục sau lỗi node.

## 20. Bảo mật và cấu hình mạng cho MPI job

MPI job cần các node giao tiếp trực tiếp hoặc thông qua transport do runtime sử dụng. Network policy quá chặt có thể chặn port động hoặc kênh control/data của MPI; mở rộng toàn bộ mạng không giới hạn lại tạo rủi ro không cần thiết.

Nguyên tắc:

- Đặt các node HPC trong subnet/private network phù hợp.
- Giới hạn inbound/outbound theo security group hoặc firewall tới các node trong cùng job/cluster.
- Xác định port/range theo MPI implementation và cấu hình launcher.
- Phân biệt kênh điều khiển của scheduler/launcher với data path giữa rank.
- Không giả định MPI luôn dùng một port cố định.
- Dùng identity, key và quyền truy cập tối thiểu cho job launch.
- Bảo vệ dữ liệu khoa học và checkpoint theo phân loại dữ liệu.
- Nếu dùng encryption, đo overhead latency/CPU và xác minh transport hỗ trợ.
- Không cho phép các job không tin cậy dùng chung network fabric hoặc host nếu isolation chưa phù hợp.

Cấu hình cụ thể phụ thuộc scheduler, MPI implementation, provider và transport. Hãy dùng hướng dẫn chính thức của môi trường cluster để mở đúng luồng cần thiết.

## 21. Triển khai một job MPI trên cluster

Một quy trình tổng quát:

1. Chọn node type đồng nhất về CPU, memory và network.
2. Chọn placement phù hợp cho các node của một job.
3. Cài cùng phiên bản MPI library, compiler runtime và dependency.
4. Xác minh node có thể phân giải tên và kết nối nhau qua private network.
5. Cấu hình scheduler, queue và resource request.
6. Chọn số node, rank mỗi node và binding.
7. Chạy smoke test MPI hai rank.
8. Chạy benchmark inter-node và collective.
9. Chạy workload thật với checkpoint và output path phù hợp.
10. Thu thập timing theo rank và network metrics.

Ví dụ job script Slurm minh họa:

~~~bash
#!/bin/bash
#SBATCH --job-name=mpi-solver
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=8
#SBATCH --time=00:30:00
#SBATCH --output=mpi-%j.out

srun --mpi=pmix ./solver
~~~

Script cần điều chỉnh theo scheduler, partition, module environment và plugin MPI của cluster. Không phải mọi Slurm cluster đều dùng pmix; một số cấu hình dùng plugin khác hoặc launcher riêng của MPI implementation.

## 22. Chọn mạng theo yêu cầu ứng dụng

Có thể phân loại ứng dụng theo pattern:

| Pattern | Đặc điểm | Yêu cầu mạng ưu tiên |
|---|---|---|
| Nhiều message nhỏ, lặp liên tục | Latency-sensitive, halo exchange | Latency thấp, jitter thấp, ít congestion |
| Truyền block dữ liệu lớn | Bandwidth-sensitive | Băng thông cao, throughput ổn định |
| Allreduce thường xuyên | Collective và synchronization | Latency thấp ở nhiều rank, topology-aware |
| All-to-all | Nhiều rank trao đổi đồng thời | Aggregate bandwidth và khả năng chịu congestion |
| Job ít giao tiếp | Compute-dominant | CPU/memory tốt; mạng phổ thông có thể đủ |
| Checkpoint lớn theo chu kỳ | Burst transfer tới storage | Băng thông và storage throughput, tránh ảnh hưởng traffic MPI |

Không chọn interconnect chỉ theo tên công nghệ hoặc tốc độ danh nghĩa. Dùng benchmark để so sánh trên topology thực tế, rồi chạy ứng dụng thật ở số node dự kiến.

## 23. Ví dụ phân tích lựa chọn cluster

Giả sử một mô phỏng CFD có 64 rank. Mỗi iteration, mỗi rank trao đổi halo với sáu neighbor và thực hiện một MPI_Allreduce nhỏ để kiểm tra residual.

Đặc điểm:

- Nhiều message nhỏ lặp lại.
- Có đồng bộ giữa các rank ở cuối iteration.
- Strong scaling khiến miền dữ liệu trên mỗi rank giảm khi tăng số rank.
- Một rank chậm có thể kéo dài iteration của toàn job.

Các bước quyết định:

1. Đo ping-pong latency giữa hai node.
2. Đo allreduce ở 64 rank và số rank mục tiêu khác.
3. So sánh placement cùng node/cluster với placement phân tán hơn nếu nền tảng cho phép.
4. Kiểm tra MPI dùng đúng high-performance transport.
5. Đo thời gian compute, halo và collective riêng.
6. Thử gộp halo message theo neighbor nếu có nhiều message nhỏ.
7. Thử nonblocking exchange để tính cell bên trong khi halo đang truyền.
8. So sánh 32, 64 và 128 rank theo thời gian hoàn thành và cost/job.

Nếu 128 rank giảm compute nhưng communication tăng khiến total time gần như không đổi, thêm node không mang lại lợi ích kinh tế. Có thể chọn 64 rank hoặc tái phân vùng bài toán.

## 24. Checklist đánh giá MPI và độ trễ mạng

- [ ] Đã xác định pattern point-to-point, collective và message size.
- [ ] Đã biết số rank, communicator và rank mapping.
- [ ] Đã phân biệt giao tiếp intra-node và inter-node.
- [ ] Đã đo latency cho message nhỏ và bandwidth cho message lớn.
- [ ] Đã benchmark collective ở số rank gần production.
- [ ] Đã đo tail latency/jitter và không chỉ average.
- [ ] Đã kiểm tra NUMA, NIC locality, CPU binding và oversubscription.
- [ ] MPI implementation chọn đúng transport và NIC.
- [ ] Đã xác minh hỗ trợ RDMA/RoCE/InfiniBand nếu workload cần.
- [ ] Placement node phù hợp với communication pattern và failure domain.
- [ ] Security group/firewall cho phép đúng control/data path của MPI.
- [ ] Đã kiểm tra MTU, packet loss, retransmission và congestion.
- [ ] Nonblocking operation tuân thủ buffer lifetime và được benchmark overlap.
- [ ] Đã profile thời gian compute, communication, collective và imbalance.
- [ ] Có checkpoint/restart hoặc kế hoạch xử lý khi node/job lỗi.
- [ ] Đã so sánh thời gian hoàn thành và cost/job ở nhiều số node.

## 25. Kết luận

MPI cho phép các tiến trình trên nhiều node trao đổi dữ liệu và phối hợp tính toán thông qua point-to-point và collective operations. Hiệu năng của ứng dụng phụ thuộc cả latency lẫn bandwidth: message nhỏ và collective thường nhạy với latency, còn truyền dữ liệu lớn nhạy với bandwidth. Khi tăng số rank, chi phí giao tiếp, đồng bộ và imbalance có thể làm strong scaling chững lại.

Để đạt hiệu năng tốt, cần thiết kế pattern giao tiếp hợp lý, giảm số message và byte truyền, overlap computation với communication khi có thể, đồng thời đặt rank phù hợp với NUMA và NIC topology. Trên cloud, hãy chọn instance và placement hỗ trợ interconnect cần thiết, xác minh MPI transport/RDMA, đo benchmark ở đúng số rank và kiểm tra tail latency. Quyết định cuối cùng phải dựa trên thời gian hoàn thành ứng dụng và cost/job thực tế, không chỉ dựa trên số vCPU hoặc băng thông quảng cáo.
