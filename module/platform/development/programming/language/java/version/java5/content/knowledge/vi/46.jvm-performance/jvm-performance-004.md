# Cơ chế JVM tự chọn cấu hình theo môi trường chạy (ergonomics)

## 1. Tại sao cùng một lệnh java lại chạy với cấu hình khác?

Bạn có thể chạy cùng một ứng dụng mà không ghi bất kỳ cờ GC hay kích thước heap nào:

```shell
java -jar application.jar
```

JVM vẫn phải quyết định cách sử dụng CPU, bộ nhớ và các thành phần thực thi. **Ergonomics** là cơ chế chọn và điều chỉnh các tham số dựa trên môi trường cùng chính sách của JVM, giúp ứng dụng có cấu hình khởi đầu hợp lý mà không cần người dùng đặt mọi chi tiết.

Tài liệu [HotSpot Ergonomics](https://docs.oracle.com/en/java/javase/25/gctuning/ergonomics.html) mô tả việc chọn mặc định cho GC, heap và trình biên dịch lúc chạy. Chi tiết thuộc cách triển khai và phiên bản JVM, không phải một công thức bất biến của ngôn ngữ Java.

Vì vậy:

- Không ghi cờ không có nghĩa JVM không có cấu hình.
- Cùng tệp JAR không bảo đảm cùng cấu hình hiệu lực trên hai môi trường.
- Cùng cấu hình khởi đầu không bảo đảm hai tải khác nhau tạo cùng hành vi khi chạy.

Bài này dùng JVM hiện đại, với các lệnh quan sát phổ biến trên HotSpot/JDK 17 trở lên. Những cờ `-XX` phải được kiểm tra trên đúng bản JVM triển khai.

## 2. Phân biệt hai giai đoạn tự chọn

### Chọn khi khởi động

JVM nhìn các đầu vào mà nó biết, chẳng hạn tài nguyên khả dụng và tùy chọn người dùng. Từ đó nó chọn các giá trị ban đầu hoặc giới hạn cho những tham số chưa được ấn định.

Ví dụ các câu hỏi JVM phải giải quyết là: heap bắt đầu và tối đa bao nhiêu, GC nào được chọn, số luồng cho một số công việc nội bộ nên là bao nhiêu.

### Điều chỉnh khi đang chạy

Sau khi ứng dụng bắt đầu, một số chính sách có thể điều chỉnh cách sử dụng tài nguyên dựa trên dữ liệu hoạt động. Mức độ tự điều chỉnh phụ thuộc GC và từng tham số.

Đừng hiểu rằng JVM luôn thay đổi mọi cờ hoặc tự đổi qua lại mọi thuật toán GC. Chọn GC khi khởi động và điều chỉnh các quyết định bên trong GC là hai việc khác nhau.

Một mô hình tư duy hữu ích:

```text
Môi trường JVM nhận biết + tùy chọn khởi động
                    |
                    v
        Cấu hình hiệu lực ban đầu
                    |
                    v
        Ứng dụng tạo tải và cấp phát
                    |
                    v
        Chính sách thích nghi được hỗ trợ
                    |
                    v
        Hành vi và số liệu quan sát
```

Các mũi tên không bảo đảm kết quả tối ưu cho mọi yêu cầu nghiệp vụ. JVM chỉ làm việc trong khả năng và ràng buộc đã có.

## 3. Môi trường được nhận biết khác tài nguyên người vận hành tưởng có

Một máy chủ có nhiều CPU và RAM nhưng tiến trình Java có thể chạy dưới giới hạn khác. Container, máy ảo và cấu hình triển khai ảnh hưởng tài nguyên JVM nhìn thấy.

Trên HotSpot Linux hỗ trợ container, JVM có thể dùng thông tin giới hạn môi trường khi xác định tài nguyên. Xem mục container trong [tài liệu lệnh java](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html). Khả năng thực tế còn phụ thuộc bản JDK, hệ điều hành và cấu hình.

Ví dụ suy luận:

```text
Máy vật lý: nhiều CPU và RAM
Container: giới hạn nhỏ hơn
JVM: cần chọn cấu hình theo tài nguyên mà nó nhận biết
```

Không lấy cấu hình trên máy phát triển rồi kết luận cùng JAR sẽ có cùng heap hoặc mức song song trong container.

Cũng không giả định JVM sẽ lập tức và hoàn toàn điều chỉnh mọi quyết định khi hạn mức tài nguyên thay đổi trong lúc chạy. Hãy kiểm chứng riêng những gì môi trường và bản JVM đang dùng thực sự hỗ trợ.

## 4. Cờ người dùng tác động như thế nào?

Ergonomics chủ yếu lấp các khoảng chưa được chỉ định và thích nghi trong phạm vi cho phép. Một lựa chọn tường minh có thể thay thế một quyết định tự chọn hoặc thu hẹp khoảng tự điều chỉnh.

Ví dụ:

| Lựa chọn | Ý nghĩa cần phân biệt |
| --- | --- |
| `-Xmx` | Đặt kích thước tối đa heap; không phải giới hạn toàn tiến trình |
| `-Xms` | Đặt kích thước heap ban đầu/tối thiểu theo cơ chế JVM hỗ trợ |
| Chọn một GC bằng cờ tương ứng | Chọn thuật toán; không tự tối ưu mọi tham số cho tải |
| `-XX:ActiveProcessorCount=N` | Thay số CPU JVM dùng cho các tính toán liên quan; không cấp thêm CPU thật |
| Mục tiêu thời gian dừng GC | Hướng chính sách tối ưu; không phải thời hạn cứng của yêu cầu ứng dụng |

`ActiveProcessorCount` được [tài liệu HotSpot](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#advanced-runtime-options-for-java) mô tả là ảnh hưởng các tính toán kích thước nhóm luồng, như GC và ForkJoinPool. Nó không thiết lập hạn mức CPU của container hoặc bảo đảm hệ điều hành luôn cho tiến trình chạy trên N CPU riêng.

Tương tự, tăng Xmx không tạo thêm RAM. Ngoài heap, tiến trình còn cần bộ nhớ cho lớp, mã biên dịch, luồng, bộ đệm và các thành phần khác. Khi đặt ngân sách bộ nhớ, phải chừa chỗ cho những phần đó.

Không sao chép một tập cờ lớn chỉ vì một hệ thống khác đã dùng nó. Cờ không cần thiết có thể chặn quyết định thích nghi hữu ích hoặc không còn phù hợp với GC/JDK mới.

## 5. Quan sát cấu hình thực tế trước khi chỉnh

### Bước 1: ghi đúng bản JVM

```shell
java -version
```

Ghi lại nhà cung cấp, phiên bản, kiến trúc và cách khởi động. Những thông tin này giúp giải thích thay đổi giữa các lần triển khai.

### Bước 2: xem thông tin VM khởi động

```shell
java -XshowSettings:vm -version
```

Trên JDK hỗ trợ, đầu ra chứa thông tin như heap tối đa được ước lượng và tên VM. Đây là một JVM mới chỉ để quan sát, không phải ảnh chụp tự động của ứng dụng đang phục vụ người dùng.

Thử đặt giới hạn heap cụ thể:

```shell
java -Xms64m -Xmx128m -XshowSettings:vm -version
```

Ở một lần chạy HotSpot phù hợp, phần thông tin VM có thể hiển thị heap tối thiểu 64M và tối đa 128M. Đây là ví dụ đọc cấu hình, không phải cấu hình đề xuất cho ứng dụng sản xuất.

Thông tin `-version` và `-XshowSettings` thường đi ra stderr. Không coi stdout trống là lệnh không in dữ liệu. Không yêu cầu đầu ra đầy đủ khớp một chuỗi cố định vì bản JDK, định dạng và môi trường có thể khác.

### Bước 3: xem các cờ hiệu lực trên HotSpot

```shell
java -XX:+PrintFlagsFinal -version
```

Lệnh này tạo nhiều đầu ra. Tìm các tên liên quan như:

```text
InitialHeapSize
MaxHeapSize
UseG1GC
UseSerialGC
ParallelGCThreads
ConcGCThreads
ActiveProcessorCount
```

Không đọc một tên cờ rồi suy ra nó chắc chắn có cùng ý nghĩa trên mọi JVM. Đây là công cụ quan sát HotSpot; nếu một triển khai không hỗ trợ, dùng công cụ tương ứng của nhà cung cấp.

Trên các bản có hiển thị nguồn gốc giá trị, nhãn như `default`, `ergonomic` hoặc `command line` giúp phân biệt mặc định, lựa chọn tự động và tùy chọn được truyền. Đừng chỉ nhìn một nhãn default rồi bỏ qua giá trị khác mà JVM đã tính từ nó.

Có thể so sánh với:

```shell
java -XX:ActiveProcessorCount=2 -XX:+PrintFlagsFinal -version
```

Quan sát các giá trị liên quan thay đổi ra sao, không đặt trước kết luận rằng mọi nhóm luồng đều trở thành đúng hai luồng.

### Bước 4: với JVM đang chạy

Khi có quyền và công cụ phù hợp, dùng:

```shell
jcmd <pid> VM.flags
jcmd <pid> VM.command_line
```

Thay `<pid>` bằng PID của đúng ứng dụng. Xem các lệnh khả dụng bằng `jcmd <pid> help`; cách sử dụng và điều kiện truy cập có trong [tài liệu jcmd](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html).

Lệnh chạy một JVM mới chỉ phản ánh môi trường/lựa chọn của lần chạy mới đó. Muốn biết ứng dụng thật, đối chiếu cấu hình hiệu lực trong tiến trình thật cùng cách môi trường đã khởi động nó.

## 6. Mục tiêu hiệu năng là sự đánh đổi

Ba mục tiêu thường phải cân bằng:

- **Thông lượng:** lượng công việc hoàn thành trong một khoảng.
- **Độ trễ:** thời gian một yêu cầu hoặc một lần dừng kéo dài.
- **Mức chiếm dụng tài nguyên:** lượng bộ nhớ/CPU cần duy trì.

Ví dụ về quyết định, không phải quy luật đảm bảo:

| Thay đổi | Lợi ích có thể mong đợi | Điều phải kiểm chứng |
| --- | --- | --- |
| Cho phép heap lớn hơn | Giảm áp lực phải thu gom thường xuyên | Bộ nhớ tổng và hành vi độ trễ |
| Nhắm thời gian dừng ngắn hơn | Giảm những đợt dừng dài | Tần suất công việc GC và thông lượng |
| Tăng mức song song nội bộ | Rút ngắn một số công việc | Tranh chấp CPU với luồng ứng dụng |
| Hạn chế mạnh bộ nhớ | Giảm mức chiếm dụng | Tần suất GC và khả năng chịu tải |

Đặc biệt, mục tiêu như `-XX:MaxGCPauseMillis` là mục tiêu cho GC hỗ trợ nó, không phải cam kết mọi lần GC đều ngắn hơn giá trị đó. Nó cũng không phải giới hạn thời gian xử lý HTTP từ đầu đến cuối. Tài liệu [Ergonomics](https://docs.oracle.com/en/java/javase/25/gctuning/ergonomics.html) mô tả việc theo đuổi mục tiêu trong các ràng buộc tài nguyên.

Nếu lượng đối tượng còn sống đã quá lớn so với heap, một cờ mục tiêu độ trễ không loại bỏ được yêu cầu bộ nhớ đó. Khi tải vượt năng lực CPU, tự chọn thêm tham số cũng không tạo năng lực tính toán mới.

## 7. Vì sao không nên khóa sớm mọi tham số?

Một tham số đặt tường minh thường dựa trên giả định về tải. Nếu tải thay đổi, giả định đó có thể không còn đúng.

Với G1, ví dụ đáng chú ý là đặt cố định kích thước thế hệ trẻ có thể hạn chế cơ chế điều chỉnh để theo đuổi mục tiêu thời gian dừng. [Hướng dẫn tinh chỉnh G1](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html) khuyến nghị bắt đầu từ cấu hình mặc định, rồi chỉ điều chỉnh có mục tiêu khi có bằng chứng.

Tình huống giả định:

```text
Ngày đầu: tải nhỏ, kích thước thế hệ trẻ cố định có vẻ tốt
Sau đó: tỷ lệ cấp phát tăng, thời gian sống đối tượng thay đổi
Kết quả: giá trị cũ trở thành giới hạn không còn phù hợp
```

Điểm cần làm không phải bỏ mọi cờ bằng mọi giá. Hãy giữ cờ có lý do cụ thể, biết nó ràng buộc điều gì và kiểm tra lại khi đổi GC, JDK, tài nguyên hoặc dạng tải.

Cũng không xem ergonomics là bộ tối ưu nghiệp vụ toàn năng. JVM không biết ứng dụng có thể bỏ bộ đệm nào, sửa truy vấn cơ sở dữ liệu ra sao hay thay đổi cấu trúc dữ liệu thế nào. Đôi khi giảm cấp phát không cần thiết trong mã hiệu quả hơn một vòng chỉnh cờ.

## 8. Quy trình điều chỉnh có thể kiểm chứng

1. **Xác định mục tiêu:** ví dụ thông lượng cần đạt, p95/p99 yêu cầu hoặc ngân sách bộ nhớ.
2. **Giữ mức nền:** ghi cấu hình hiệu lực và chạy tải đại diện.
3. **Tìm giới hạn:** CPU, bộ nhớ, GC, I/O hay thời gian chờ.
4. **Đổi ít biến:** nêu rõ giả thuyết mỗi thay đổi định kiểm tra.
5. **Đo lại:** so sánh cùng điều kiện và đủ thời gian qua giai đoạn làm nóng.
6. **Giữ hoặc bỏ:** ghi kết quả và lý do, không chỉ giữ vì biểu đồ một lần trông đẹp.

Tập dữ liệu quan sát có thể gồm thông lượng, phân bố độ trễ, GC, heap sau thu gom, CPU và bộ nhớ tiến trình/container. Không dùng riêng thời gian GC tích lũy để tuyên bố hiệu năng toàn ứng dụng đã tốt hơn.

Khi so sánh hai môi trường, kiểm tra cả cấu hình JVM và năng lực thực cấp. Nếu đồng thời đổi JDK, CPU, giới hạn RAM và cờ GC, rất khó quy kết nguyên nhân cho một thay đổi.

## 9. Những kết luận dễ sai

**“Mặc định là một con số chung cho Java.”**  
Mặc định phụ thuộc triển khai, phiên bản và bối cảnh. Hãy quan sát cấu hình hiệu lực.

**“Tăng số CPU JVM nhìn thấy sẽ làm ứng dụng có thêm CPU.”**  
Cờ nhận biết CPU không thay thế tài nguyên thật.

**“Xmx bằng giới hạn container thì dùng hết RAM hiệu quả nhất.”**  
Heap chỉ là một phần bộ nhớ tiến trình; cần ngân sách cho các phần khác.

**“Đã đặt mục tiêu dừng 50 ms thì mọi yêu cầu dưới 50 ms.”**  
Đó không phải cam kết của GC hay của đường xử lý yêu cầu.

**“Một lần java -version chứng minh ứng dụng thật đang chạy cấu hình đó.”**  
Lần chạy mới có thể khác cách khởi động hoặc môi trường của tiến trình thật.

**“Heap thay đổi kích thước nghĩa là JVM bất ổn.”**  
Cần xem đó có phải thích nghi bình thường và mục tiêu ứng dụng có đạt không.

## 10. Thực hành quan sát

Chạy các lệnh quan sát ở mục 5, ghi lại:

- Bản JDK và tên VM.
- Heap tối đa khi không chỉ định Xmx.
- Heap tối đa khi đặt Xmx128m.
- Các cờ có nguồn gốc từ dòng lệnh hoặc từ quyết định tự chọn.
- Sự thay đổi khi đặt ActiveProcessorCount=2, nếu JVM hỗ trợ.

Không dùng kết quả trên máy cá nhân làm tiêu chuẩn bắt buộc cho container hay máy chủ khác. Kết quả học tập cần đạt là giải thích được **JVM đã nhìn thấy gì, đã chọn gì, người dùng đã ràng buộc gì và dữ liệu nào xác nhận hiệu quả thực tế**.
