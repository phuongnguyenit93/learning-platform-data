Điều kiện phản xạ của equals yêu cầu điều gì đối với tham chiếu x không null?
A. x.equals(null) phải true khi x là một đối tượng.
B. x.equals(x) phải true với mọi đối tượng x hợp lệ.
C. x.equals(y) phải true nếu x và y cùng kiểu lớp.
D. x.equals(y) phải true nếu x và y cùng hashCode.
Đáp án đúng: B

Với mọi đối tượng Java không null x, kết quả hợp lệ của x.equals(null) là gì?
A. Trả về true nếu lớp của x cho phép giá trị null.
B. Ném NullPointerException theo mặc định hợp đồng.
C. Trả về false, vì null không đại diện một đối tượng.
D. Phụ thuộc vào giá trị hashCode() hiện tại của x.
Đáp án đúng: C

Nếu một lớp không ghi đè equals(Object), quy tắc so sánh kế thừa từ Object là gì?
A. Hai tham chiếu bằng nhau khi các trường giống nhau.
B. Hai tham chiếu bằng nhau khi toString() giống nhau.
C. Hai tham chiếu bằng nhau khi hashCode() trùng nhau.
D. Hai tham chiếu phải cùng trỏ đến một đối tượng.
Đáp án đúng: D

Hai tham chiếu cùng kiểu trỏ đến hai đối tượng riêng biệt nhưng có cùng dữ liệu. Nhận định nào đúng?
A. == đúng; equals tùy thuộc cách cài đặt của lớp.
B. == sai; equals có thể đúng nếu lớp so sánh theo giá trị.
C. == sai; equals bắt buộc phải sai trong mọi lớp.
D. == đúng; equals bắt buộc phải đúng khi các trường trùng.
Đáp án đúng: B

Phát biểu nào thể hiện tính đối xứng trong hợp đồng equals?
A. a.equals(b) đúng thì a.hashCode() phải dương.
B. a.equals(b) đúng kéo theo a.equals(c) luôn đúng.
C. a.equals(b) sai thì a.hashCode() phải khác.
D. a.equals(b) đúng kéo theo b.equals(a) cũng đúng.
Đáp án đúng: D

Điều kiện bắc cầu của equals được diễn đạt chính xác như thế nào?
A. a bằng b và b bằng c thì a cũng phải bằng c.
B. a bằng b thì hai đối tượng phải cùng tham chiếu.
C. a bằng b thì mọi đối tượng cùng lớp đều bằng nhau.
D. a khác b thì hai đối tượng bắt buộc khác mã hash.
Đáp án đúng: A

Khi nào hai lần gọi x.equals(y) liên tiếp được phép cho kết quả khác nhau mà không vi phạm hợp đồng?
A. Thông tin tham gia equals của x hoặc y đã thay đổi.
B. Lần gọi thứ hai diễn ra trên một luồng thực thi khác.
C. Trình thu gom rác đã chạy giữa hai lần so sánh.
D. hashCode() của một đối tượng vừa được gọi thêm.
Đáp án đúng: A

Lớp khai báo boolean equals(MyClass other) nhưng không có equals(Object other). Hệ quả nào đúng?
A. Đây là override; mọi lời gọi Object đều dùng phương thức mới.
B. Biên dịch thất bại vì Java cấm overload phương thức equals.
C. Đây là overload; equals(Object) kế thừa vẫn hoạt động.
D. Java tự tạo cầu nối equals(Object) tới phương thức overload.
Đáp án đúng: C

Tác dụng thiết thực của @Override khi khai báo equals(Object) là gì?
A. Tự sinh phần thân so sánh khi lập trình viên chưa viết mã.
B. Báo lỗi biên dịch khi chữ ký không ghi đè phương thức cha.
C. Bảo đảm hashCode() khớp equals lúc chạy mà không cần sửa.
D. Tự thêm kiểm tra null và kiểm tra lớp cho mọi lời gọi.
Đáp án đúng: B

Trong lớp giá trị chỉ chấp nhận so bằng nhau khi cùng lớp cụ thể, kiểm tra getClass() trong equals giúp điều gì?
A. Cho phép lớp con thêm trường mà vẫn luôn bằng lớp cha.
B. Khiến hai đối tượng có mã hash trùng nhau được coi là bằng nhau.
C. Chỉ đối tượng có cùng lớp cụ thể mới được so là bằng nhau.
D. Cho phép so sánh với mọi lớp triển khai cùng interface.
Đáp án đúng: C

Vì sao equals dựa vào instanceof ở lớp cha có thể gây lỗi khi lớp con thêm trường so sánh riêng?
A. Lớp con sẽ không được phép ghi đè equals của lớp cha.
B. Mọi phép so sánh giữa cha và con luôn gây lỗi runtime.
C. instanceof sẽ tự bỏ qua toàn bộ các trường của lớp cha.
D. Có thể phá đối xứng do cha và con so các trường khác nhau.
Đáp án đúng: D

Khi xây dựng lớp giá trị bất biến, tập trường đưa vào equals nên được chọn thế nào?
A. Chọn mọi trường tạm dùng để cache kết quả nội bộ.
B. Chọn các trường được thêm gần nhất vào phiên bản lớp.
C. Chọn mã hash của đối tượng để khỏi so dữ liệu thật.
D. Chọn các trường xác định danh tính giá trị của lớp.
Đáp án đúng: D

Quy tắc quan trọng nhất giữa equals và hashCode là gì?
A. a.equals(b) đúng thì mã hash của chúng phải bằng nhau.
B. Hai mã hash bằng nhau thì hai đối tượng phải bằng nhau.
C. Hai đối tượng khác nhau thì mã hash luôn khác nhau.
D. Nếu lớp có equals thì được phép bỏ qua hashCode.
Đáp án đúng: A

Hai đối tượng không bằng nhau nhưng có cùng hashCode() có vi phạm hợp đồng Java không?
A. Có, mỗi đối tượng phải có hash duy nhất lúc chạy.
B. Có, HashSet không thể giữ hai đối tượng cùng hash.
C. Không, nên HashMap không cần gọi equals để tra khóa.
D. Không, đối tượng khác nhau vẫn có thể cùng hash.
Đáp án đúng: D

Khi thông tin liên quan đến phép so sánh không thay đổi, hashCode() cần đáp ứng điều gì?
A. Các lần gọi trên hai máy phải trả cùng số nguyên.
B. Hash ổn định giữa các lần gọi trong cùng một lần chạy.
C. Giá trị trả về luôn phải là một số nguyên không âm.
D. Giá trị phải thay đổi sau mỗi lần gọi equals.
Đáp án đúng: B

Phát biểu nào đúng về giá trị trả về của Object.hashCode() mặc định?
A. Đó luôn là địa chỉ vùng nhớ đối tượng trên heap.
B. Đó luôn là giá trị ngẫu nhiên mới ở mỗi lần gọi.
C. Giá trị int không được bảo đảm là địa chỉ heap.
D. Đó là số thứ tự tạo đối tượng theo toàn bộ JVM.
Đáp án đúng: C

Objects.equals(a,b) làm gì khi cả a và b đều là null?
A. Trả false vì null không đại diện một đối tượng.
B. Trả true vì hai tham chiếu đầu vào đều là null.
C. Ném NullPointerException khi cố gọi a.equals(b).
D. Chỉ trả true nếu hai biến khai báo cùng một kiểu.
Đáp án đúng: B

Kết quả của Objects.hashCode(null) là gì?
A. Trả 0 theo hợp đồng của tiện ích Objects.hashCode.
B. Ném NullPointerException khi gọi null.hashCode().
C. Trả mã hash của lớp Object cho giá trị null.
D. Trả mã hash mặc định khác nhau theo từng JVM.
Đáp án đúng: A

Khi xây dựng hashCode cho lớp có các trường quyết định equals, cách nào phù hợp nhất?
A. Chỉ kết hợp các trường bị thay đổi thường xuyên nhất.
B. Chỉ dùng hash của tên lớp và bỏ qua mọi trường.
C. Kết hợp những trường được dùng trong phép equals.
D. Chỉ dùng số thứ tự tạo đối tượng trong bộ nhớ.
Đáp án đúng: C

Với hai mảng int[] khác tham chiếu nhưng có phần tử giống nhau, phép kiểm tra nào so nội dung?
A. a.equals(b) tự so sánh từng phần tử theo thứ tự.
B. a == b so sánh các phần tử tương ứng trong mảng.
C. Arrays.equals(a,b) so sánh nội dung hai mảng.
D. Objects.equals(a,b) luôn so sánh từng phần tử.
Đáp án đúng: C

Khi so sánh nội dung hai mảng lồng nhau kiểu Object[][], lựa chọn phù hợp là gì?
A. Arrays.equals(a,b) luôn so sánh sâu mọi mức lồng.
B. a.equals(b) tự động so nội dung của tất cả mảng.
C. a == b dùng phép so sánh sâu cho mảng hai chiều.
D. Arrays.deepEquals(a,b) so sánh sâu phần tử mảng.
Đáp án đúng: D

Một record chứa thành phần kiểu int[] và dùng equals được sinh tự động. Điều nào đúng?
A. Các mảng cùng phần tử luôn khiến hai record bằng nhau.
B. record tự dùng Arrays.deepEquals cho mọi thành phần mảng.
C. Các mảng khác tham chiếu có thể khiến record khác nhau.
D. record không được phép khai báo thành phần kiểu mảng.
Đáp án đúng: C

Với String s1 = new String("hi") và s2 = new String("hi"), nhận định nào đúng?
A. equals là true, còn == là false đối với hai chuỗi.
B. s1 == s2 là true vì chuỗi được tự động intern.
C. s1.equals(s2) là false vì đối tượng tách biệt.
D. Hai hashCode khác nhau vì hai tham chiếu không trùng.
Đáp án đúng: A

Một khóa đã thêm vào HashMap rồi bị đổi trường tham gia equals/hashCode. Nguy cơ gì xuất hiện?
A. HashMap tự tính lại vị trí khóa ngay sau mỗi thay đổi.
B. Lần tìm sau có thể thất bại do vị trí băm cũ.
C. Cặp khóa–giá trị tự động bị loại khỏi map khi sửa khóa.
D. Sửa trường chỉ ảnh hưởng toString, không ảnh hưởng tra cứu.
Đáp án đúng: B

HashMap.put(k2,v2) được gọi khi map đã có khóa k1 với k1.equals(k2) và hash khớp. Kết quả là gì?
A. Ghi đè giá trị của khóa tương đương; size không tăng.
B. Map thêm khóa khác vì k1 và k2 là hai tham chiếu.
C. Map ném lỗi do hai khóa bằng nhau theo equals.
D. Map giữ giá trị cũ và bỏ qua lệnh put thứ hai.
Đáp án đúng: A

Một HashSet đã có đối tượng a; thêm b với a.equals(b) và hash bằng nhau. add(b) trả gì?
A. true, vì b là một đối tượng khác tham chiếu.
B. true, nhưng HashSet đồng thời xóa phần tử a.
C. false, vì tập đã chứa phần tử tương đương.
D. Ném ngoại lệ vì hai phần tử dùng chung mã hash.
Đáp án đúng: C

Hai khóa khác nhau nhưng có cùng hash được đưa vào HashMap. Điều kiện nào giúp lưu được cả hai?
A. equals của hai khóa trả false dù hashCode giống nhau.
B. toString giữa hai khóa phải trả hai chuỗi khác nhau.
C. Hai khóa phải thuộc hai lớp Java khác nhau để tránh đụng hash.
D. Hai khóa phải có địa chỉ heap khác tại thời điểm put.
Đáp án đúng: A

Nếu mọi đối tượng của một lớp trả về cùng hashCode, nhận định nào chính xác?
A. Java luôn ném lỗi khi thêm đối tượng thứ hai vào HashSet.
B. equals của lớp đó bắt buộc phải luôn trả true.
C. Tra cứu trong HashMap luôn có thời gian hằng số.
D. Hợp đồng vẫn có thể đúng, nhưng hiệu năng HashMap dễ giảm.
Đáp án đúng: D

Khi dò khóa trong một bucket băm có nhiều ứng viên, vai trò của equals là gì?
A. Thay thế hoàn toàn việc tính hash khi tìm bucket.
B. Phân biệt các khóa trùng hash nhưng không bằng nhau.
C. Thay đổi vị trí bộ nhớ của các khóa đã lưu.
D. Chỉ định thứ tự tăng dần của các khóa trong bucket.
Đáp án đúng: B

Với HashMap tiêu chuẩn, nhận định nào đúng về khóa null?
A. Cho phép một khóa null, ánh xạ đến một giá trị.
B. Map từ chối mọi khóa null bằng ngoại lệ bắt buộc.
C. Map cho phép nhiều khóa null như các khóa khác nhau.
D. Map chỉ nhận khóa null nếu hashCode bị ghi đè.
Đáp án đúng: A

Hai BigDecimal lần lượt tạo từ chuỗi "1.0" và "1.00". Điều nào đúng?
A. equals true và compareTo cũng trả về 0.
B. equals false, compareTo 0 do khác scale.
C. equals true nhưng compareTo lại trả số khác 0.
D. equals và compareTo đều phân biệt khác biệt scale.
Đáp án đúng: B

Thêm new BigDecimal("1.0") và new BigDecimal("1.00") vào TreeSet dùng thứ tự tự nhiên. Tập sẽ ra sao?
A. Luôn giữ cả hai vì equals phân biệt phần scale.
B. Ném lỗi vì TreeSet không hỗ trợ phần tử BigDecimal.
C. Chỉ một phần tử vì compareTo trả 0 giữa hai giá trị.
D. Tự đổi scale của hai phần tử để equals khớp nhau.
Đáp án đúng: C

Hợp đồng Comparable.compareTo quy định ý nghĩa giá trị âm, 0 và dương là gì?
A. Dấu âm, 0, dương biểu thị nhỏ, ngang thứ tự, lớn.
B. Biểu thị khác đối tượng, cùng tham chiếu, cùng kiểu tương ứng.
C. Biểu thị âm vô hạn, bằng số 0, dương vô hạn tương ứng.
D. Biểu thị nhỏ hơn, bằng equals, có cùng hash tương ứng.
Đáp án đúng: A

Quy tắc đối dấu quan trọng của compareTo đối với a và b là gì?
A. a.compareTo(b) luôn bằng đúng -b.compareTo(a).
B. a.compareTo(b) luôn bằng a.hashCode() - b.hashCode().
C. Dấu của a.compareTo(b) ngược dấu b.compareTo(a).
D. a.compareTo(b) luôn trả một trong ba số -1, 0, 1.
Đáp án đúng: C

Điều kiện bắc cầu nào cần có khi xây dựng thứ tự tự nhiên với compareTo?
A. Nếu a > b và b > c thì a.equals(c) phải đúng.
B. Nếu a > b và b > c thì a > c theo compareTo.
C. Nếu a > b và b > c thì mọi hashCode phải tăng.
D. Nếu a > b và b > c thì thứ tự tham chiếu tăng.
Đáp án đúng: B

Quan hệ nào giữa compareTo và equals được khuyến nghị khi xây dựng thứ tự tự nhiên?
A. compareTo bằng 0 khi và chỉ khi equals trả true.
B. compareTo bằng 0 khi và chỉ khi hai đối tượng cùng hash.
C. compareTo bằng 0 khi và chỉ khi hai tham chiếu trùng nhau.
D. compareTo bằng 0 khi và chỉ khi toString bằng nhau.
Đáp án đúng: A

Một Comparator chỉ so tuổi của hai Person. Hai người khác ID nhưng cùng tuổi có thể thế nào?
A. Comparator bắt buộc so ID trước rồi mới so tuổi.
B. equals tự động trả true chỉ vì comparator trả 0.
C. Comparator ném ngoại lệ nếu hai người cùng tuổi.
D. Comparator có thể trả 0 dù equals trả false.
Đáp án đúng: D

Cách xây dựng comparator nào so trường int age mà tránh lỗi tràn do phép trừ?
A. (a,b) -> a.age() - b.age() luôn an toàn với mọi giá trị.
B. (a,b) -> a.hashCode() - b.hashCode() phản ánh thứ tự tuổi.
C. (a,b) -> a.toString().compareTo(b.toString()) so tuổi chuẩn.
D. Comparator.comparingInt(Person::age) an toàn với int.
Đáp án đúng: D

Trong triển khai compareTo cho hai giá trị int bất kỳ, nên dùng lựa chọn nào?
A. a - b vì dấu của hiệu không bao giờ bị tràn.
B. Integer.compare(a,b) tránh tràn số khi lấy hiệu.
C. Math.abs(a - b) mã hóa cả lớn hơn và nhỏ hơn.
D. Objects.hash(a,b) cho biết thứ tự tăng dần.
Đáp án đúng: B

Với comparator byName.thenComparing(byAge), comparator thứ hai được dùng khi nào?
A. Khi phép so sánh tên làm phát sinh bất kỳ ngoại lệ nào.
B. Khi hai đối tượng có tên khác nhau theo comparator.
C. Khi so sánh theo tên cho kết quả 0 thì mới so tuổi.
D. Khi hai đối tượng luôn bằng nhau theo phương thức equals.
Đáp án đúng: C

Với Comparator.nullsFirst(byName), phần tử null được xử lý như thế nào?
A. Null bị loại khỏi danh sách trước khi so các phần tử.
B. Null đứng sau phần tử không null, bất kể byName.
C. Null luôn gây NullPointerException khi đem đi so sánh.
D. Null đứng trước các phần tử khác; còn lại theo byName.
Đáp án đúng: D

Một danh sách được sort theo Comparator.comparing(Person::name). Điều gì đúng về equals?
A. Sắp xếp tự thay equals để chỉ so trường tên mỗi đối tượng.
B. Comparator phải trả 0 đúng khi equals trả true.
C. Sort chỉ thành công nếu Person ghi đè cả equals và hashCode.
D. Việc sort không tự thay cách Person.equals so sánh.
Đáp án đúng: D

Với TreeMap có comparator chỉ theo id, đưa vào hai khóa khác tham chiếu nhưng cùng id sẽ thế nào?
A. Khóa cùng id tương đương; giá trị cũ bị thay.
B. Map lưu hai ánh xạ vì chỉ equals quyết định khóa.
C. Map luôn ném lỗi vì comparator trả 0 cho hai khóa.
D. Map dùng hashCode để tách khóa thành hai bucket.
Đáp án đúng: A

Thêm hai chuỗi "abc" và "ABC" vào TreeSet dùng String.CASE_INSENSITIVE_ORDER cho kết quả gì?
A. Chỉ giữ một chuỗi do comparator không phân biệt hoa/thường.
B. Tập giữ cả hai vì String.equals vẫn phân biệt chữ hoa.
C. Tập ném lỗi vì comparator không nhất quán với equals.
D. Tập biến hai chuỗi về chữ thường rồi lưu cả hai.
Đáp án đúng: A

Khi ghi đè toString cho lớp nghiệp vụ, mục đích sử dụng an toàn và hợp lý nhất là gì?
A. Tạo khóa duy nhất để thay cho equals trong mọi collection.
B. Mô tả dễ đọc để debug và không làm lộ dữ liệu nhạy cảm.
C. Bảo đảm chuỗi kết quả không đổi giữa các phiên bản.
D. Xác thực dữ liệu rồi cập nhật trạng thái trước khi in.
Đáp án đúng: B

Nếu một lớp chỉ kế thừa Object.toString(), dạng thông tin trả về về cơ bản là gì?
A. Tên lớp kèm danh sách đầy đủ các trường khai báo.
B. Đường dẫn tệp bytecode của lớp và thời gian khởi tạo.
C. Chuỗi JSON tự động chứa mọi trường public của lớp.
D. Tên lớp kèm @ và hash dạng thập lục phân.
Đáp án đúng: D

Với biến Object x = null, kết quả giữa String.valueOf(x) và x.toString() khác nhau gì?
A. Cả hai đều ném NullPointerException khi nhận null.
B. Cả hai đều trả chuỗi "null" nhờ tự động ép kiểu.
C. valueOf trả chuỗi "null", còn toString ném lỗi.
D. String.valueOf(x) trả chuỗi rỗng; x.toString() trả null.
Đáp án đúng: C

Lớp ghi đè equals để so mã định danh, nhưng giữ hashCode mặc định từ Object. Rủi ro là gì?
A. JVM từ chối khởi tạo đối tượng khi hai phương thức chưa khớp.
B. Khóa bằng nhau có thể có hash khác, khiến tìm sai trong map.
C. equals sẽ tự gọi Object.hashCode thay vì so mã định danh.
D. HashMap bỏ qua mã hash và chỉ dùng toString để so khóa.
Đáp án đúng: B
