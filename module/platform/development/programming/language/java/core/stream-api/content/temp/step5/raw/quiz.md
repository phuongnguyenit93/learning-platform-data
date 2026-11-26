Câu 1. Với `Stream.of(1, 2, 3).map(x -> x * 2)` chưa có terminal operation, điều gì đúng?
A. Phép map chạy trên một thread riêng trước khi có terminal.
B. Map chưa xử lý phần tử vì chưa có terminal operation.
C. Phép map lưu sẵn kết quả vào List sau khi được khai báo.
D. Phép map tính xong ba kết quả ngay lúc tạo pipeline.
Đáp án đúng: B

Câu 2. Trong các lời gọi sau trên `Stream<String>`, đâu là terminal operation?
A. `filter(s -> !s.isEmpty())` lọc phần tử trong stream.
B. `map(String::trim)` tạo một stream đã biến đổi.
C. `collect(Collectors.toList())` là terminal operation.
D. `peek(System.out::println)` quan sát phần tử đi qua.
Đáp án đúng: C

Câu 3. Với `Stream<Integer> s = Stream.of(1, 2); s.count();`, gọi tiếp `s.toList()` sẽ thế nào?
A. Tạo lại pipeline từ nguồn rồi tính lại danh sách.
B. `s.toList()` ném `IllegalStateException` vì s đã tiêu thụ.
C. Trả List gồm 1 và 2 vì nguồn vẫn còn phần tử.
D. Trả List rỗng vì count đã dịch con trỏ tới cuối.
Đáp án đúng: B

Câu 4. Kết quả `Stream.of(1,2,3,4).filter(n -> n % 2 == 0).map(n -> n * 3).toList()` là gì?
A. List `[6, 12]` gồm các số chẵn sau khi nhân ba.
B. List `[3, 6, 9, 12]` vì map chạy trước filter.
C. List `[2, 4]` gồm các số chẵn trước khi nhân ba.
D. List `[1, 2, 3, 4]` vì filter không có tác dụng.
Đáp án đúng: A

Câu 5. Với `List<List<Integer>> groups`, thao tác nào tạo `Stream<Integer>` từ các phần tử bên trong?
A. `groups.stream().map(List::stream)` trả các Integer.
B. `groups.stream().filter(List::stream)` trả các Integer.
C. `groups.stream().flatMap(List::stream)` trả các Integer.
D. `groups.stream().peek(List::stream)` trả các Integer.
Đáp án đúng: C

Câu 6. `Stream.mapMulti` hữu ích khi một phần tử đầu vào sinh nhiều hoặc không sinh phần tử nào vì lý do gì?
A. Callback có thể đẩy không, một hoặc nhiều output tới consumer.
B. Callback chỉ biến đổi kiểu phần tử mà giữ nguyên số lượng.
C. Callback phải trả một stream mới cho mỗi phần tử đầu vào.
D. Callback tự động gọi terminal để chuyển dữ liệu thành List.
Đáp án đúng: A

Câu 7. Biểu thức `Stream.iterate(1, n -> n + 1).limit(3).toList()` trả về gì?
A. List `[1, 2, 3]` lấy ba phần tử đầu của luồng vô hạn.
B. List `[0, 1, 2]` vì giới hạn đếm trước phần tử khởi đầu.
C. List `[1, 2]` vì limit(3) loại phần tử có giá trị bằng 3.
D. Không kết thúc vì iterate là nguồn vô hạn không thể giới hạn.
Đáp án đúng: A

Câu 8. Trên stream tuần tự, `anyMatch(p)` có thể dừng sớm khi nào?
A. Khi đã gặp phần tử đầu tiên không thỏa p.
B. Khi đã xử lý toàn bộ các phần tử thỏa p.
C. Khi một phần tử bất kỳ bị loại bởi filter trước đó.
D. Khi gặp phần tử thỏa p và xác định kết quả true.
Đáp án đúng: D

Câu 9. Trên parallel stream có encounter order, cách nào yêu cầu chọn phần tử đầu theo thứ tự đó?
A. Dùng `parallel().findAny()` để bảo đảm chọn phần tử đầu.
B. Dùng `unordered().findFirst()` để khôi phục thứ tự gốc.
C. Dùng `findFirst()` vì nó tôn trọng encounter order.
D. Dùng `findAny()` thay vì `findFirst()` để giữ ngữ nghĩa thứ tự.
Đáp án đúng: C

Câu 10. Với ordered stream các object trùng nội dung theo `equals`, `distinct()` hoạt động thế nào?
A. Giữ phần tử đầu cho mỗi giá trị bằng nhau theo `equals`.
B. Sắp xếp object rồi dùng Comparator để xét trùng.
C. Loại các object cùng tham chiếu theo toán tử `==`.
D. Giữ lần cuối của các object có cùng class để tránh trùng.
Đáp án đúng: A

Câu 11. Kết quả của `Stream.of("b", "a", "c").sorted().toList()` là gì?
A. List `[a, c, b]` vì sorted ưu tiên chuỗi đầu vào.
B. List `[b, a, c]` vì sorted không đổi encounter order.
C. List `[c, b, a]` vì sorted mặc định giảm dần.
D. List `[a, b, c]` theo natural order của String.
Đáp án đúng: D

Câu 12. Vì sao không nên dùng `peek` làm nơi duy nhất cập nhật trạng thái nghiệp vụ?
A. Peek cam kết gọi callback đúng một lần mỗi phần tử nguồn.
B. Peek là terminal operation nên callback chạy ngay khi tạo.
C. Peek tự đồng bộ trạng thái mutable giữa parallel workers.
D. Peek có thể không chạy nếu không cần thực thi phần tử.
Đáp án đúng: D

Câu 13. Giá trị của `Stream.of(1,2,3).reduce(0, Integer::sum)` là bao nhiêu?
A. `1` vì reduce dừng sau phần tử đầu tiên.
B. `0` vì identity được giữ nguyên dù có phần tử.
C. `6` là tổng ba phần tử với identity bằng 0.
D. `3` vì reduce chỉ lấy phần tử cuối của stream.
Đáp án đúng: C

Câu 14. Khi gọi `Stream.<Integer>empty().reduce(Integer::sum)`, kết quả thuộc trường hợp nào?
A. `Optional.of(0)` vì phép cộng tự dùng identity 0.
B. `Optional.of(1)` vì sum bắt đầu với giá trị mặc định.
C. `Optional.empty()` vì stream không có phần tử để gộp.
D. `null` vì reduce không trả về Optional trên stream rỗng.
Đáp án đúng: C

Câu 15. Với `List<Integer> xs = Stream.of(1, 2).toList();`, `xs.add(3)` gây điều gì?
A. `add(3)` ném `UnsupportedOperationException`.
B. Trả false vì List từ Stream chỉ chặn phần tử khác kiểu.
C. Thêm 3 vào xs vì Stream.toList trả ArrayList mutable.
D. Thêm 3 vào stream gốc rồi tạo lại danh sách kết quả.
Đáp án đúng: A

Câu 16. Về List trả từ `Collectors.toList()`, API Java cam kết điều gì?
A. Cam kết List có thread-safe iterator và random access.
B. Cam kết List không thể chỉnh sửa như Stream.toList().
C. Cam kết List luôn là một ArrayList có thể thêm phần tử.
D. Không cam kết kiểu List hay khả năng sửa đổi.
Đáp án đúng: D

Câu 17. Với `Stream.of("a","bb","c").collect(groupingBy(String::length))`, `get(1)` nhận gì?
A. List `[a, c]` của các chuỗi có độ dài bằng 1.
B. Giá trị số `2` biểu thị số chuỗi độ dài 1.
C. List `[bb]` của chuỗi có độ dài bằng 2.
D. List `[a, bb, c]` vì groupingBy không thực hiện nhóm.
Đáp án đúng: A

Câu 18. `Collectors.partitioningBy(n -> n % 2 == 0)` tạo kết quả dạng nào?
A. List hai phần tử Boolean cho mỗi đầu vào của stream.
B. Map với khóa Integer đại diện phần dư phép chia.
C. Map với hai khóa Boolean nhóm phần tử theo predicate.
D. Set chứa các phần tử thỏa predicate và bỏ phần còn lại.
Đáp án đúng: C

Câu 19. `Collectors.toMap(Item::id, Item::name)` gặp hai Item trùng id khác tên, mặc định gây gì?
A. Ném `IllegalStateException` vì khóa trùng không có merge.
B. Nối hai tên thành một String khi khóa id bị trùng.
C. Giữ item đầu tiên khi khóa bị trùng mà không cần merge.
D. Giữ item cuối cùng khi khóa id bị trùng nhau.
Đáp án đúng: A

Câu 20. Với `Stream.of("a","b")` tuần tự, `toMap(String::length, x->x, (a,b)->a+b).get(1)` là gì?
A. Chuỗi `"a"` vì toMap giữ phần tử có khóa 1 đầu tiên.
B. Chuỗi `"ab"` vì merge nối các giá trị cùng khóa 1.
C. Ném exception vì toMap không chấp nhận merge function.
D. Chuỗi `"b"` vì toMap ghi đè bằng phần tử cuối.
Đáp án đúng: B

Câu 21. Trong collector `groupingBy(Person::dept, mapping(Person::name, toList()))`, giá trị map là gì?
A. Map chỉ đếm số lượng người trong từng phòng ban.
B. Một tên duy nhất được chọn cho mỗi phòng ban.
C. List tên người thuộc từng phòng ban theo khóa dept.
D. List đối tượng Person thuộc từng phòng ban theo dept.
Đáp án đúng: C

Câu 22. `Collectors.teeing(c1, c2, merger)` được dùng để làm gì?
A. Chọn c1 hoặc c2 tùy giá trị phần tử đầu tiên.
B. Chạy c1 trước rồi dùng kết quả c1 làm stream đầu vào c2.
C. Chia phần tử vào hai nhánh dựa trên một predicate Boolean.
D. Chạy hai downstream collector và gộp kết quả bằng merger.
Đáp án đúng: D

Câu 23. Trong custom Collector dùng trên parallel stream, `combiner` có nhiệm vụ chính gì?
A. Thêm một phần tử stream vào container đang xử lý.
B. Gộp các accumulator cục bộ trong parallel pipeline.
C. Chuyển container cuối thành kiểu kết quả sau khi gom.
D. Tạo container đầu tiên cho một lần thu thập.
Đáp án đúng: B

Câu 24. Đặc tính `Collector.Characteristics.IDENTITY_FINISH` nói gì về finisher?
A. Collector tự đồng bộ khi nhiều thread cùng cập nhật.
B. Finisher phải tạo object mới từ mỗi accumulator.
C. Accumulator có thể dùng trực tiếp làm kết quả.
D. Collector bỏ qua accumulator và chỉ dùng combiner.
Đáp án đúng: C

Câu 25. Với ordered parallel stream, `forEach` có đảm bảo thứ tự encounter không?
A. Có; forEach giữ đúng encounter order trên mọi stream.
B. Không; các callback có thể thực thi khác thứ tự nguồn.
C. Không; forEach chỉ chạy một callback dù có nhiều phần tử.
D. Có; forEach ép toàn bộ pipeline chạy trên một thread.
Đáp án đúng: B

Câu 26. Với ordered parallel stream, `forEachOrdered` khác `forEach` ở điểm nào?
A. Biến stream thành unordered trước khi thực hiện action.
B. Tôn trọng encounter order khi chạy action trên phần tử.
C. Trả về List mới thay vì thực hiện terminal action.
D. Bỏ qua những phần tử xử lý chậm để hoàn tất sớm.
Đáp án đúng: B

Câu 27. Vì sao thêm phần tử vào một `ArrayList` dùng chung từ `parallelStream().forEach(...)` có thể lỗi?
A. ArrayList tự biến thành immutable khi tạo stream song song.
B. Parallel stream ngăn truy cập vào mọi object có thể sửa.
C. ForEach trên parallel stream chỉ cho phép thread-local array.
D. ArrayList không đồng bộ cho thao tác ghi đồng thời.
Đáp án đúng: D

Câu 28. `Spliterator.tryAdvance(action)` trả boolean với ý nghĩa nào?
A. `true` khi đã xử lý toàn bộ phần tử còn lại.
B. `true` nếu đã xử lý một phần tử, `false` khi hết.
C. `false` khi Spliterator có đặc tính `ORDERED`.
D. `false` khi action không thay đổi phần tử được truyền.
Đáp án đúng: B

Câu 29. Khi `trySplit()` thành công trên một ordered Spliterator, kết quả thường là gì?
A. Iterator mới bỏ qua mọi phần tử đã chia trước đó.
B. Spliterator mới chứa prefix, bản gốc giữ phần còn lại.
C. Collector mới chứa kết quả sau khi chạy terminal operation.
D. Spliterator mới chứa toàn bộ phần tử và bản gốc giữ nguyên.
Đáp án đúng: B

Câu 30. Khi đọc file bằng `Files.lines(path)` để xử lý qua stream, nên quản lý tài nguyên thế nào?
A. Dùng try-with-resources để đóng stream sau khi xử lý.
B. Chỉ đóng Path vì stream không giữ tài nguyên hệ thống.
C. Đợi garbage collector đóng stream thay cho ứng dụng.
D. Gọi `parallel()` để JVM tự đóng nguồn file sau terminal.
Đáp án đúng: A

Câu 31. Trên JDK 24+, `stream.gather(Gatherers.windowFixed(3))` tạo kiểu dữ liệu nào?
A. Các List có đúng ba phần tử kể cả cửa sổ cuối.
B. Ba Stream riêng biệt chạy song song với nhau.
C. Một List chứa ba phần tử đầu, các phần tử sau bỏ qua.
D. Các List cửa sổ tối đa ba phần tử theo thứ tự nguồn.
Đáp án đúng: D

Câu 32. Trên JDK 24+, `Stream.of(1,2,3).gather(Gatherers.scan(() -> 0, Integer::sum)).toList()` trả gì?
A. List `[0, 1, 3, 6]` có thêm identity trước dữ liệu.
B. List `[6]` chứa kết quả sau khi gom toàn bộ stream.
C. List `[1, 2, 3]` giữ nguyên các giá trị đầu vào.
D. List `[1, 3, 6]` là các tổng tích lũy theo phần tử.
Đáp án đúng: D
