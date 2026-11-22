# ArrayList: khởi tạo, tăng dung lượng và chi phí thêm cuối khấu hao

Khi đọc các dòng dữ liệu mà chưa biết trước số dòng, ta cần một danh sách có thể nhận thêm phần tử. Mảng Java có độ dài cố định sau khi tạo; nếu tự dùng mảng, ta phải theo dõi số phần tử, phát hiện lúc đầy, cấp mảng khác và chuyển dữ liệu. `ArrayList` đóng gói công việc đó để người dùng thao tác với một danh sách có chỉ số.

Sự thuận tiện này có một chi phí cần hiểu: phần lớn lần thêm cuối chỉ ghi thêm một tham chiếu, nhưng một số lần phải thay mảng lưu trữ. Vì vậy, câu “thêm cuối là O(1)” chỉ chính xác khi nói về **chi phí hằng số khấu hao trên một chuỗi thao tác**, không phải thời gian tối đa của từng lần gọi.

Bài này đi từ mô hình kích thước–dung lượng, các cách khởi tạo, cơ chế tăng mảng, đến chứng minh khấu hao và cách chọn chiến lược cấp phát. Ví dụ dùng API tương thích Java 17. Chi tiết riêng của một bản OpenJDK được tách khỏi những điều chương trình có thể dựa vào qua API.

## 1. Hai đại lượng khác nhau: số phần tử và chỗ dự trữ

**Kích thước (size)** là số phần tử đang thuộc về danh sách. **Dung lượng (capacity)** là số vị trí mà mảng nền hiện có thể chứa trước khi cần tăng tiếp.

Ta có thể hình dung một danh sách như sau:

~~~text
size = 3, capacity = 5

chi so mang:   0      1      2      3      4
             [A]    [B]    [C]   [rong] [rong]
              <--- phan tu --->  <- du tru ->
~~~

Sơ đồ là mô hình giải thích. `[rong]` biểu diễn vị trí dự trữ bên trong, không phải một phần tử có thể đọc bằng `get`. Với trạng thái này:

- `size()` trả về 3.
- `get(0)`, `get(1)`, `get(2)` hợp lệ.
- `get(3)` không hợp lệ dù mảng nền còn chỗ.
- `add("D")` tạo phần tử thứ tư của danh sách.
- `set(3, "D")` trước khi thêm không hợp lệ; `set` chỉ thay một phần tử đã tồn tại.

Điều kiện cần giữ là:

~~~text
0 <= size <= capacity

get/set:      0 <= index < size
add(index,x): 0 <= index <= size
~~~

Trong đó `add(size, x)` là chèn ở cuối; `add(x)` diễn đạt trực tiếp mục đích này.

Dung lượng không phải giới hạn số phần tử mà danh sách được phép nhận suốt đời. Khi cần, danh sách có thể tăng thêm dung lượng, miễn là môi trường còn cấp phát được bộ nhớ. Ngược lại, dung lượng lớn không làm danh sách có sẵn phần tử.

### 1.1. Một phần tử null vẫn được tính vào size

`ArrayList` cho phép phần tử `null`. Nếu gọi `add(null)`, ta đã thêm một phần tử và `size` tăng lên. Không được đồng nhất “vị trí có tham chiếu null” với “vị trí chưa thuộc danh sách”.

Điều quyết định phần nào của mảng là nội dung danh sách chính là `size`. Đây cũng là lý do không thể suy ra kích thước bằng cách quét đến tham chiếu `null` đầu tiên.

### 1.2. Mảng nền chứa tham chiếu

Với `ArrayList<Person>`, các vị trí mảng giữ tham chiếu tới đối tượng `Person`. Tăng mảng sao chép các tham chiếu; nó không tạo bản sao sâu của từng `Person`.

Tương tự, `ArrayList<Integer>` không phải `int[]` tự tăng. Nó chứa tham chiếu tới các đối tượng `Integer`; việc đóng hộp (boxing), bộ nhớ của đối tượng và cách các giá trị được tạo là những chi phí khác với chi phí thay mảng. Khi phân tích thêm cuối, cần nói rõ đang đếm công việc ở cấu trúc danh sách hay toàn bộ công việc của ứng dụng.

## 2. Chọn cách khởi tạo theo thông tin đang có

Ba dạng khởi tạo thường dùng:

| Cách viết | Kích thước ngay sau tạo | Mục đích |
|---|---:|---|
| `new ArrayList<>()` | 0 | Chưa có dữ liệu, chưa có ước lượng hữu ích |
| `new ArrayList<>(expected)` | 0 | Dự trữ theo số phần tử dự kiến |
| `new ArrayList<>(source)` | `source.size()` nếu nguồn ổn định | Tạo danh sách chứa các phần tử của nguồn |

Tham số số nguyên là dung lượng ban đầu, không phải kích thước ban đầu. Constructor nhận collection sao chép phần tử theo thứ tự bộ lặp của nguồn; nó không tự sắp xếp. Dung lượng âm gây `IllegalArgumentException`; collection nguồn là `null` gây `NullPointerException`. Xem hợp đồng tại [ArrayList trong Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

### 2.1. Constructor mặc định: lựa chọn tốt khi chưa biết số lượng

Đoạn sau là một phần thân phương thức minh họa:

~~~java
ArrayList<String> names = new ArrayList<>();
names.add("An");
names.add("Binh");
~~~

Người dùng không cần tự quản lý việc đầy mảng. Đây thường là cách viết rõ ràng khi danh sách có quy mô nhỏ, hoặc chưa có số lượng dự kiến đáng tin.

Không cần chọn một con số lớn tùy ý để “phòng trường hợp thiếu”. Việc tự tăng là chức năng bình thường của cấu trúc này; quyết định đặt trước dung lượng cần có lý do từ dữ liệu hoặc phép đo.

### 2.2. Constructor số nguyên: dành chỗ, chưa điền dữ liệu

~~~java
ArrayList<String> names = new ArrayList<>(100);
~~~

Dòng trên tạo danh sách rỗng có dung lượng ban đầu được chỉ định. Nó không tạo 100 tên rỗng, 100 chuỗi rỗng hay 100 phần tử `null`. Ngay sau đó, `names.size()` vẫn bằng 0.

Nếu muốn danh sách thực sự có 100 phần tử `null`, phải thêm 100 phần tử; đó là yêu cầu khác và làm thay đổi nội dung quan sát được. Không dùng thao tác điền phần tử giả để thay cho yêu cầu dự trữ bộ nhớ.

Giá trị 0 hợp lệ: `new ArrayList<>(0)` vẫn có thể nhận phần tử về sau. Giá trị âm không mang nghĩa “để Java tự tính”. Nếu ước lượng có thể âm, hãy xử lý lỗi đầu vào trước khi gọi constructor.

Đặt trước dung lượng hợp lý hữu ích khi biết sẽ thu thập khoảng 20.000 kết quả. Nó dời công việc cấp phát sang thời điểm khởi tạo và giảm những lần thay mảng khi thêm. Tuy nhiên, nếu cuối cùng chỉ nhận 3 kết quả, phần lớn vùng dự trữ chưa phục vụ nội dung thực tế.

### 2.3. Constructor collection: sao chép cấu trúc, chia sẻ phần tử

~~~java
ArrayList<String> names = new ArrayList<>(List.of("An", "Binh"));
names.add("Chi");
~~~

Danh sách mới có thể thay đổi cấu trúc dù nguồn `List.of` không cho phép thêm hoặc xóa. Điều này thuận tiện khi cần bắt đầu từ một tập dữ liệu cố định rồi tiếp tục chỉnh sửa.

Cần phân biệt hai loại độc lập:

- Thêm hoặc xóa trong danh sách mới không trực tiếp thêm hoặc xóa phần tử của danh sách nguồn.
- Nếu phần tử là đối tượng có thể thay đổi và cả hai danh sách cùng giữ tham chiếu đến nó, thay đổi đối tượng có thể được nhìn thấy qua cả hai danh sách.

Ví dụ đầy đủ ở phần thực hành dùng `StringBuilder` để quan sát hiện tượng này. Sao chép danh sách không tự biến các đối tượng bên trong thành bất biến hoặc độc lập.

Nếu nguồn có m phần tử, việc thiết lập nội dung danh sách mới cần xử lý các phần tử nguồn; không nên coi constructor này là thao tác O(1) chỉ vì cú pháp có một dòng. Với nguồn thông thường, ổn định và có thao tác duyệt tuyến tính, chi phí sao chép là O(m). Nếu nguồn có cách triển khai đặc biệt hoặc bị thay đổi đồng thời, phải xét hợp đồng và chi phí của chính nguồn.

### 2.4. “Mặc định 10” có nghĩa gì?

Tài liệu Java 17 mô tả constructor không tham số với dung lượng ban đầu 10. Điều đó không có nghĩa là `size()` bằng 10 hay chương trình được phép đọc 10 vị trí.

Ở bản OpenJDK 17 được tham chiếu trong bài, constructor mặc định dùng một mảng rỗng đánh dấu và trì hoãn cấp mảng thông thường đến lúc cần. Với lần thêm đầu tiên thông thường, mốc mặc định là 10. Constructor truyền 0 đi qua một trạng thái rỗng khác; không nên dùng hai cách tạo này để suy đoán một lịch tăng giống nhau. Đây là chi tiết triển khai, thể hiện trong [mã nguồn ArrayList của OpenJDK 17, bản jdk-17+35](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/ArrayList.java).

Kết luận để viết mã là: cả hai cách đều tạo danh sách rỗng hợp lệ, và ứng dụng sử dụng `size`, `add`, `get` theo hợp đồng. Không viết điều kiện nghiệp vụ dựa trên việc lần cấp mảng đầu tiên có đúng 10 vị trí.

## 3. Điều gì xảy ra khi thêm cuối?

Xét một danh sách đang có n phần tử và dung lượng c. Có hai tình huống.

### 3.1. Còn chỗ: ghi ở vị trí kế tiếp

Nếu `n < c`, cấu trúc có thể:

1. Ghi tham chiếu phần tử mới vào vị trí n.
2. Tăng kích thước thành n + 1.

Không cần dịch các phần tử phía trước. Nếu chỉ xét công việc quản lý mảng và chỉ số, số thao tác không tăng theo n: đây là đường đi có chi phí O(1).

Việc tạo phần tử có thể tốn nhiều thời gian hơn. Với `list.add(loadLargeDocument())`, tải tài liệu xảy ra trước khi lời gọi `add` nhận được kết quả; đánh giá tốc độ toàn biểu thức phải tính riêng công việc đó.

### 3.2. Đã đầy: thay mảng rồi mới ghi

Nếu `n == c`, cấu trúc cần một vùng chứa lớn hơn. Mô hình điển hình là:

1. Chọn dung lượng mới đủ chứa ít nhất phần tử sắp thêm.
2. Cấp một mảng mới.
3. Sao chép dữ liệu từ mảng cũ.
4. Chuyển tham chiếu nội bộ sang mảng mới.
5. Ghi phần tử mới và cập nhật kích thước.

Ví dụ minh họa dưới đây cố ý dùng một chính sách tăng giả định:

~~~text
truoc add(D): size=3, capacity=3
mang cu:       [A] [B] [C]

sau khi tang: size=3, capacity=6
mang moi:      [A] [B] [C] [ ] [ ] [ ]

sau add(D):   size=4, capacity=6
mang moi:      [A] [B] [C] [D] [ ] [ ]
~~~

Sơ đồ không khẳng định `ArrayList` Java luôn tăng từ 3 lên 6. Nó giải thích vì sao một lần thêm có thể cần công việc tỷ lệ với số phần tử hiện có.

Khi tăng từ một mảng đầy, sao chép n tham chiếu đã có tạo chi phí O(n). Cấp phát và khởi tạo mảng mới cũng có chi phí; phân tích khấu hao phải xét cả chuỗi lần tăng, thay vì chỉ bỏ qua các bước đắt.

### 3.3. Danh sách vẫn là cùng một đối tượng

Khi mảng nền được thay, đối tượng `ArrayList` mà mã ứng dụng đang giữ không bị thay bằng một danh sách mới. Các biến cùng trỏ tới danh sách đó vẫn thấy nội dung được thêm.

Các phần tử cũng không đổi danh tính chỉ vì mảng chứa tham chiếu của chúng được thay. Không có yêu cầu gọi lại constructor của từng phần tử, `clone` từng phần tử hay tính lại nội dung nghiệp vụ.

Mảng cũ có thể trở thành đối tượng đủ điều kiện để bộ gom rác thu hồi sau khi không còn tham chiếu cần thiết. Điều này không bảo đảm bộ nhớ được thu hồi ngay lập tức. Trong lúc chuyển tiếp, cần có chỗ cho cả mảng cũ và mảng mới; đỉnh sử dụng bộ nhớ có thể cao hơn kích thước ổn định sau khi tăng.

## 4. Chính sách tăng dung lượng: cam kết và chi tiết triển khai

Điều ứng dụng cần dựa vào là khả năng tự tăng và cam kết thêm cuối có chi phí hằng số khấu hao. API không cố định một hệ số tăng mà mọi Java implementation phải dùng.

Ở OpenJDK 17 được nêu trên, khi đã có mảng thông thường, mức tăng ưu tiên xấp xỉ một nửa dung lượng cũ. Mức tối thiểu cần thiết và xử lý giới hạn số nguyên có thể làm kết quả khác phép nhân 1,5 đơn giản. Việc tính chiều dài liên quan đến [ArraysSupport của cùng bản OpenJDK](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/jdk/internal/util/ArraysSupport.java).

Không cần ghi nhớ một dãy dung lượng để sử dụng `ArrayList` đúng. Những nhận định sau đều thiếu điều kiện:

- “Mọi lần tăng đều gấp đôi.”
- “Mọi lần tăng đều đúng 1,5 lần, kể cả mảng rỗng và số nhỏ.”
- “Sau khi thêm n phần tử, dung lượng chắc chắn bằng một công thức cố định của n.”
- “Constructor hoặc `ensureCapacity` sẽ luôn cấp đúng số ô mà tôi có thể kiểm tra bằng một getter.”

`ArrayList` không cung cấp phương thức công khai `capacity()`. `size()` chỉ báo số phần tử. Không dùng reflection vào trường riêng để biến chi tiết triển khai thành điều kiện nghiệp vụ hoặc thành một kiểm thử tính đúng của ứng dụng.

Bài sẽ dùng chính sách **tăng gấp đôi** ở phần toán học và chương trình đếm công việc. Chính sách này giúp nhìn rõ cấp số nhân. Nó là mô hình học tập riêng, không phải bản sao thuật toán OpenJDK.

## 5. Vì sao một số lần O(n) vẫn cho thêm cuối O(1) khấu hao?

### 5.1. Xét tổng chi phí của một chuỗi, không chỉ lần chậm nhất

Giả sử bắt đầu rỗng và chỉ thêm cuối. Trong mô hình tăng gấp đôi, dung lượng đi qua:

~~~text
1, 2, 4, 8, 16, 32, ...
~~~

Để chuyển từ mảng đầy sang mảng kế tiếp, ta sao chép:

~~~text
0, 1, 2, 4, 8, 16, ...
~~~

Đa số lần thêm nằm giữa hai mốc tăng và không sao chép phần tử cũ. Một lần tăng đắt tạo ra nhiều chỗ trống, phục vụ nhiều lần thêm tiếp theo.

Bảng đếm công việc với 9 lần thêm:

| Lần thêm | Dung lượng sau thêm | Số phần tử cũ phải sao chép ở lần này | Ghi phần tử mới |
|---:|---:|---:|---:|
| 1 | 1 | 0 | 1 |
| 2 | 2 | 1 | 1 |
| 3 | 4 | 2 | 1 |
| 4 | 4 | 0 | 1 |
| 5 | 8 | 4 | 1 |
| 6 | 8 | 0 | 1 |
| 7 | 8 | 0 | 1 |
| 8 | 8 | 0 | 1 |
| 9 | 16 | 8 | 1 |

Sau 9 lần thêm, tổng có 15 lượt sao chép và 9 lượt ghi mới. Riêng lần thứ 9 làm nhiều việc hơn lần thứ 8, nhưng tổng công việc vẫn chỉ tỷ lệ với số phần tử đã thêm.

### 5.2. Chứng minh bằng tổng cấp số nhân

Gọi n là số phần tử đã thêm, n >= 1; gọi C là dung lượng cuối trong mô hình tăng gấp đôi. Ta có:

~~~text
n <= C < 2n

tong so tham chieu/phan tu cu duoc sao chep
    = 1 + 2 + 4 + ... + C/2
    = C - 1
    < 2n

so lan ghi phan tu moi = n

tong hai loai cong viec < 3n
~~~

Với C = 1, tổng sao chép rỗng bằng 0; công thức C - 1 vẫn đúng.

Vì tổng công việc cho n lần thêm là O(n), chia cho n thao tác cho ta chi phí O(1) khấu hao mỗi lần thêm. Đây là một giới hạn trên cho cả chuỗi theo mô hình, không cần giả định người dùng đưa vào dữ liệu ngẫu nhiên.

Chi phí cấp phát và khởi tạo mảng không làm mất kết quả bậc lớn này trong mô hình thông thường: tổng các chiều dài mảng đã cấp cũng là một tổng cấp số nhân và là O(n). Tuy nhiên, các hằng số, cách JVM cấp phát, bộ gom rác và phần tử mà ứng dụng tạo đều ảnh hưởng thời gian thực.

### 5.3. Khấu hao khác trung bình xác suất và khác giới hạn độ trễ

**Phân tích khấu hao (amortized analysis)** phân bổ tổng công việc của một chuỗi thao tác. Nó không nói “thường thì dữ liệu may mắn nên nhanh”.

Nếu chương trình phải đáp ứng hạn thời gian rất chặt cho từng yêu cầu, một lần sao chép lớn vẫn có thể làm yêu cầu đó chậm. O(1) khấu hao không phải cam kết rằng mỗi lần gọi có cùng số nano giây, không cấp phát hay không gặp dừng do bộ gom rác.

Ba câu nên dùng với đúng phạm vi:

| Câu hỏi | Kết luận phù hợp |
|---|---|
| Thêm cuối khi còn chỗ tốn bao nhiêu công việc quản lý danh sách? | O(1) |
| Một lần thêm cuối có thể làm bao nhiêu việc khi cần tăng từ mảng đầy? | O(n), với n là số phần tử cũ |
| Một chuỗi n lần thêm cuối từ rỗng, theo chính sách tăng thông thường, có tổng công việc bậc nào? | O(n), tức O(1) khấu hao mỗi lần |

Nếu danh sách ban đầu đã có m phần tử, lần thêm đầu tiên của đoạn đang quan sát có thể phải chuyển m phần tử đó. Không được cắt bỏ lịch sử rồi tuyên bố một chuỗi rất ngắn luôn chỉ tốn theo số phần tử mới. Một giới hạn an toàn cho việc thêm tiếp n phần tử từ trạng thái đã có m phần tử là O(m + n), nếu tính cả lần tăng liên quan.

### 5.4. Vì sao không chỉ tăng thêm một vị trí?

Nếu mỗi lần đầy chỉ cấp đúng một vị trí bổ sung, số lần sao chép khi thêm n phần tử từ rỗng là:

~~~text
0 + 1 + 2 + ... + (n - 1) = n(n - 1)/2
~~~

Tổng trở thành O(n²). Cấp thừa một phần dung lượng giúp đổi bộ nhớ dự trữ lấy ít lần sao chép hơn.

Với hệ số tăng cố định lớn hơn 1, tổng chiều dài các đợt vẫn có dạng cấp số nhân. Hệ số lớn hơn thường tạo nhiều chỗ dư hơn sau một lần tăng nhưng giảm tần suất tăng; hệ số gần 1 thường giảm chỗ dư nhưng làm tổng sao chép có hằng số lớn hơn. Đây là đánh đổi về thiết kế cấu trúc dữ liệu, không phải một tham số công khai để chỉnh trên `ArrayList`.

## 6. ensureCapacity và trimToSize điều khiển điều gì?

### 6.1. ensureCapacity: chuẩn bị trước một nhu cầu có căn cứ

Với một danh sách đã tồn tại, có thể gọi:

~~~java
ArrayList<String> rows = new ArrayList<>();
rows.ensureCapacity(20_000);
~~~

Yêu cầu này không thêm phần tử. Nó cũng không điền `null`, không đổi thứ tự và không làm các chỉ số từ 0 đến 19.999 trở thành chỉ số đọc hợp lệ.

Tên “capacity” cần hiểu theo mức tối thiểu phục vụ nhu cầu, không phải lệnh đặt dung lượng bằng chính xác tham số. Nếu đã đủ chỗ, không cần tăng. Nếu cần tăng, triển khai có thể chọn một mảng lớn hơn mức yêu cầu. Phương thức này không dùng để thu nhỏ.

Ở đường đi của constructor mặc định trong OpenJDK 17, những yêu cầu nhỏ còn có thể giữ trạng thái cấp phát lười đã nêu. Bởi vậy, không suy ra rằng mỗi lần gọi `ensureCapacity(k)` đều thực hiện cấp phát ngay.

Khi sẽ bổ sung một lô dữ liệu, nhu cầu là **tổng kích thước cần có sau bổ sung**, không chỉ số phần tử của lô. Nếu hiện có 3.000 phần tử và dự kiến thêm 2.000, một yêu cầu theo 2.000 không diễn đạt nhu cầu 5.000 phần tử.

Phép tính `size + incomingCount` dùng số nguyên `int` có thể tràn nếu dữ liệu quá lớn. Nếu ứng dụng thực sự nhận các số lượng bên ngoài có thể lớn, hãy kiểm tra không âm và tràn số, chẳng hạn bằng `Math.addExact`, rồi áp dụng giới hạn bộ nhớ của ứng dụng. Một tổng còn nằm trong `int` chưa bảo đảm cấp phát thành công.

Không cần gọi `ensureCapacity(size() + 1)` trước mọi lần `add`: chính `add` đã có khả năng tăng. Mặt khác, cũng không được khẳng định chuỗi lời gọi dư thừa này mặc nhiên ép mỗi lần tăng đúng một vị trí; `ensureCapacity` đặt mức cần thiết, không cố định cách tăng. Muốn kết luận về hiệu năng phải phân tích đúng hành vi.

### 6.2. trimToSize: bỏ phần dự trữ không dùng

`trimToSize()` yêu cầu thu dung lượng về kích thước hiện có. Nó giữ nguyên nội dung logic của danh sách.

Nếu danh sách từng có rất nhiều phần tử rồi chỉ còn một phần nhỏ và sẽ giữ lâu để đọc, việc thu gọn có thể giảm phần mảng dự trữ. Nếu danh sách sắp được thêm nhiều trở lại, thu gọn có thể chỉ khiến lần thêm sau phải tăng mảng.

Đây không phải thao tác O(1) vô điều kiện. Trong triển khai dùng mảng, khi thực sự cần thu gọn, phải cấp mảng mới và chuyển dữ liệu còn giữ. Chi phí và bộ nhớ tạm trong lúc sao chép vẫn cần được tính.

### 6.3. clear giải phóng nội dung danh sách, không hứa trả ngay toàn bộ bộ nhớ

`clear()` làm danh sách rỗng, nên `size()` về 0. Ở OpenJDK 17, các tham chiếu phần tử bị xóa khỏi các vị trí đang dùng, còn mảng nền được giữ lại. Việc giữ mảng có ích nếu cùng danh sách được tái sử dụng cho đợt tiếp theo.

Đừng suy ra rằng gọi `clear` thì mọi đối tượng phần tử lập tức biến mất khỏi heap. Chúng có thể còn được nơi khác tham chiếu; ngay cả khi không còn, thời điểm bộ gom rác thu hồi vẫn do JVM quyết định.

Nếu vừa xóa một tập rất lớn và chắc chắn không cần giữ vùng dự trữ, có thể cân nhắc `trimToSize` sau đó, hoặc thay đổi cách quản lý vòng đời danh sách. Quyết định phải xét ai còn giữ tham chiếu tới danh sách cũ và nhu cầu dùng lại, không chỉ nhìn một lần đo bộ nhớ.

### 6.4. Đừng thu gọn sau mỗi lần thêm

Giả sử sau mỗi `add` đều gọi `trimToSize`. Kết thúc mỗi vòng lặp, dung lượng lại bằng kích thước; lần thêm tiếp theo không còn chỗ dự trữ.

Ở cấu trúc mảng đang xét, việc đó khiến các lần thêm liên tiếp phải sao chép danh sách ngày càng dài, và thu gọn còn có thể sao chép thêm lần nữa. Tổng chi phí có thể trở thành O(n²). Chính chương trình đã phá điều kiện giữ lại khoảng trống để phân bổ chi phí.

Trường hợp này khác một lần thu gọn có chủ đích sau khi hoàn thành giai đoạn nạp dữ liệu. Không nên biến một thao tác tối ưu bộ nhớ có điều kiện thành nghi thức bắt buộc trong vòng lặp.

## 7. Thực hành: quan sát API và đếm công việc trong mô hình riêng

Chương trình sau có hai phần độc lập:

1. Dùng `ArrayList` thật để kiểm tra kích thước, chỉ số, constructor, `ensureCapacity`, `trimToSize` và sao chép nông.
2. Dùng `DoublingBuffer` tự viết để đếm công việc tăng gấp đôi, vì API `ArrayList` không có bộ đếm số lần sao chép hay getter dung lượng.

`DoublingBuffer` cố ý đơn giản và dùng `int[]`. Nó không triển khai `List`, không có đủ thao tác hay chính sách giới hạn của `ArrayList`, và không dùng cho dữ liệu sản xuất. Mục tiêu duy nhất là kiểm tra phép cộng đã chứng minh.

### 7.1. Mã nguồn hoàn chỉnh

Lưu thành `ArrayListGrowthDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ArrayListGrowthDemo {
    // Mo hinh de dem cong viec: KHONG phai ma nguon ArrayList.
    static final class DoublingBuffer {
        private int[] elements = new int[0];
        private int size;
        private long copies;
        private int growths;

        void add(int value) {
            if (size == elements.length) {
                int nextCapacity = elements.length == 0
                        ? 1 : Math.multiplyExact(elements.length, 2);
                copies += size;
                elements = Arrays.copyOf(elements, nextCapacity);
                growths++;
            }
            elements[size++] = value;
        }

        long totalWork() {
            return copies + size;
        }
    }

    public static void main(String[] args) {
        ArrayList<String> defaults = new ArrayList<>();
        ArrayList<String> zero = new ArrayList<>(0);
        ArrayList<String> reserved = new ArrayList<>(4);
        System.out.printf("empty sizes: default=%d, zero=%d, reserved=%d%n",
                defaults.size(), zero.size(), reserved.size());

        try {
            reserved.get(0);
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("get(0) before add: IndexOutOfBoundsException");
        }

        reserved.add("A");
        reserved.add("B");
        System.out.printf("after add: size=%d, values=%s%n",
                reserved.size(), reserved);
        reserved.ensureCapacity(100);
        System.out.printf("after ensureCapacity: size=%d, values=%s%n",
                reserved.size(), reserved);
        reserved.trimToSize();
        System.out.printf("after trimToSize: size=%d, values=%s%n",
                reserved.size(), reserved);
        reserved.clear();
        System.out.printf("after clear: size=%d, values=%s%n",
                reserved.size(), reserved);

        ArrayList<String> mutable = new ArrayList<>(List.of("X", "Y"));
        mutable.add("Z");
        System.out.println("copy from List.of: " + mutable);
        try {
            new ArrayList<String>(-1);
        } catch (IllegalArgumentException exception) {
            System.out.println("negative capacity: IllegalArgumentException");
        }

        ArrayList<StringBuilder> source = new ArrayList<>();
        source.add(new StringBuilder("item"));
        ArrayList<StringBuilder> copied = new ArrayList<>(source);
        source.add(new StringBuilder("other"));
        copied.get(0).append("*");
        System.out.printf("shallow copy: sourceSize=%d, copySize=%d, shared=%s%n",
                source.size(), copied.size(), source.get(0) == copied.get(0));
        System.out.printf("shared content: source=%s, copy=%s%n",
                source.get(0), copied.get(0));

        System.out.println("doubling model: n, capacity, growths, copies, stores, work");
        for (int n : new int[] {1, 2, 3, 4, 5, 8, 9, 16, 17, 1000}) {
            DoublingBuffer buffer = new DoublingBuffer();
            for (int value = 0; value < n; value++) {
                buffer.add(value);
            }
            System.out.printf("%d, %d, %d, %d, %d, %d%n",
                    n, buffer.elements.length, buffer.growths,
                    buffer.copies, buffer.size, buffer.totalWork());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 ArrayListGrowthDemo.java
java ArrayListGrowthDemo
~~~

### 7.2. Kết quả stdout

~~~text
empty sizes: default=0, zero=0, reserved=0
get(0) before add: IndexOutOfBoundsException
after add: size=2, values=[A, B]
after ensureCapacity: size=2, values=[A, B]
after trimToSize: size=2, values=[A, B]
after clear: size=0, values=[]
copy from List.of: [X, Y, Z]
negative capacity: IllegalArgumentException
shallow copy: sourceSize=2, copySize=1, shared=true
shared content: source=item*, copy=item*
doubling model: n, capacity, growths, copies, stores, work
1, 1, 1, 0, 1, 1
2, 2, 2, 1, 2, 3
3, 4, 3, 3, 3, 6
4, 4, 3, 3, 4, 7
5, 8, 4, 7, 5, 12
8, 8, 4, 7, 8, 15
9, 16, 5, 15, 9, 24
16, 16, 5, 15, 16, 31
17, 32, 6, 31, 17, 48
1000, 1024, 11, 1023, 1000, 2023
~~~

### 7.3. Đọc kết quả

Dòng `empty sizes` cho thấy ba cách tạo rỗng đều có cùng kích thước logic. Nó không đo dung lượng thực và không khẳng định ba mảng nền có cùng cách cấp phát.

Ngoại lệ ở `get(0)` chứng minh dung lượng dự trữ không mở rộng miền chỉ số hợp lệ. Chương trình chỉ in tên loại ngoại lệ do chính nó chọn, không phụ thuộc nội dung thông báo ngoại lệ riêng của từng JDK.

Các dòng sau `ensureCapacity` và `trimToSize` vẫn cho `size=2`, `values=[A, B]`. Đây là điều quan sát được qua API: nội dung được giữ. Chương trình không cố đọc trạng thái riêng để đo bao nhiêu ô đã cấp.

Bản sao từ `List.of` nhận thêm `Z` thành công. Trong ví dụ `StringBuilder`, thêm một đối tượng vào nguồn làm kích thước nguồn thành 2, bản sao vẫn có 1 phần tử; nhưng đối tượng đầu tiên được chia sẻ nên cả hai cùng nhìn thấy `item*`.

Ở bảng `doubling model`:

- `n` là số lần thêm từ một bộ đệm rỗng mới.
- `capacity` là chiều dài mảng của mô hình tự viết, không phải của `ArrayList`.
- `growths` đếm số đợt cấp mảng, gồm lần đầu từ 0 lên 1.
- `copies` đếm tổng số phần tử cũ phải chuyển giữa các mảng.
- `stores` đếm một lượt ghi cho mỗi phần tử mới.
- `work` là `copies + stores`.

Tại n = 16, tổng công việc được đếm là 15 + 16 = 31. Tại n = 17, thêm một phần tử vượt mốc 16 làm tổng sao chép tăng lên 31, nhưng tổng công việc 48 vẫn nhỏ hơn 3 × 17. Tại n = 1.000, 2.023 đơn vị vẫn tăng tuyến tính theo n.

Bộ đếm này không bao gồm khởi tạo các ô mảng mới, tính toán chỉ số, kiểm tra điều kiện, thu gom rác hay thời gian tạo phần tử. Vì vậy, không đọc 2.023 thành 2.023 nano giây, và không so sánh trực tiếp số đó với thời gian thực của Java `ArrayList`. Nó minh chứng một mô hình chi phí đã được công bố rõ.

## 8. Chọn chiến lược cấp phát trong ứng dụng

### 8.1. Biết số lượng đầu ra tương đối chắc

Nếu biết đầu ra có đúng hoặc gần k phần tử và k hợp lý với ngân sách bộ nhớ, dùng `new ArrayList<>(k)` giúp tránh nhiều đợt tăng trong quá trình nạp.

Hãy tính cả chi phí khởi tạo vùng chứa vào quá trình xây danh sách. Đặt trước k rất lớn không biến toàn bộ quá trình thành miễn phí; nó dời chi phí cấp mảng ra đầu và giữ bộ nhớ sớm hơn.

Nếu đưa việc tạo danh sách ra ngoài đoạn đo thời gian, kết quả đo chỉ phản ánh phần còn lại. Điều này có thể đúng với mục tiêu đo, nhưng phải được nói rõ khi so sánh với cách để danh sách tự tăng.

### 8.2. Chỉ biết cận trên rất lỏng

Giả sử có 1.000.000 bản ghi đầu vào nhưng chỉ một phần nhỏ qua bộ lọc. Dùng số đầu vào làm dung lượng đầu ra có thể lãng phí đáng kể.

Có thể chọn mặc định, một ước lượng dựa trên tỷ lệ kết quả đã quan sát, hoặc xử lý theo từng lô. Không có quy tắc “biết cận trên thì luôn cấp bằng cận trên”. Một ước lượng nhỏ vừa phải vẫn cho phép tăng nếu thực tế lớn hơn.

Không cấp phát theo một số lượng cực lớn do người dùng hoặc dữ liệu ngoài cung cấp mà chưa áp dụng giới hạn ứng dụng. Constructor nhận `int` hợp lệ về mặt kiểu chưa chứng minh rằng yêu cầu phù hợp với bộ nhớ đang có.

### 8.3. Danh sách tăng theo nhiều đợt

Nếu từng đợt bổ sung có số lượng biết trước, có thể chuẩn bị theo tổng nhu cầu trước đợt. Đừng đặt `trimToSize` giữa các đợt chỉ để vài giây sau lại tăng.

Nếu một danh sách sống lâu nhưng tải cao chỉ xảy ra một lần, việc giữ mảng lớn mãi có thể không phù hợp. Tách pha nạp, pha xử lý và vòng đời dữ liệu giúp quyết định thời điểm thu gọn hoặc bỏ danh sách rõ ràng hơn.

### 8.4. Cần kiểm soát độ trễ của một lần thêm

Đặt trước dung lượng có thể tránh tăng mảng trong một khoảng đã dự kiến. Tuy nhiên, nó không tự bảo đảm thời gian tối đa cho toàn ứng dụng: tạo phần tử, truy cập dữ liệu, lập lịch luồng và bộ gom rác vẫn còn.

Nếu yêu cầu quan trọng là độ trễ đuôi, cần đo phân bố độ trễ trên tải phù hợp và thiết kế vòng đời bộ nhớ tương ứng. Một giá trị trung bình tốt không chứng minh không có lần thêm chậm ở ranh giới dung lượng.

### 8.5. Khi không cần giữ toàn bộ kết quả

Nếu chỉ cần tính tổng, ghi từng bản ghi hoặc chuyển tiếp theo luồng, hãy xem có thật sự cần tích lũy mọi phần tử trong danh sách không. Tránh lưu trữ không cần thiết có thể có tác động lớn hơn việc điều chỉnh dung lượng.

Đây là quyết định về thuật toán và yêu cầu đầu ra. Nếu cần truy cập lại toàn bộ dữ liệu theo chỉ số, giữ danh sách có thể hoàn toàn hợp lý; không thay cấu trúc chỉ vì muốn loại bỏ một lần tăng mảng.

## 9. Giới hạn của kết luận hiệu năng

### 9.1. Đặt trước dung lượng không làm mọi thao tác thành O(1)

Dung lượng đủ chỗ tránh chi phí thay mảng, nhưng chèn ở đầu vẫn phải dời các phần tử phía sau. Tương tự, xóa ở giữa cần xử lý khoảng trống.

Với `ArrayList`, mô hình chi phí thường dùng là:

| Thao tác | Công việc chính |
|---|---|
| `get(index)`, `set(index, value)` | Truy cập vị trí đã có, O(1) |
| `add(value)` | O(1) khấu hao; có lần tăng O(n) |
| `add(index, value)` | Dịch phần đuôi, có thể O(n), cộng khả năng tăng mảng |
| Tìm phần tử bằng cách duyệt | Có thể phải xem n phần tử |
| Thu gọn mảng thực sự | Cấp mảng khác và chuyển dữ liệu còn giữ |

Độ phức tạp mô tả số lượng công việc tăng theo đầu vào. Nó không thay thế việc đo một ứng dụng có phần tử lớn, thao tác so sánh tốn kém hoặc giới hạn heap cụ thể.

### 9.2. Bộ nhớ không chỉ là n phần tử

Cần phân biệt dung lượng mảng tham chiếu, đối tượng danh sách, đối tượng phần tử và bộ nhớ tạm khi tăng. Không thể tính chính xác số byte bằng một công thức cố định “n × 4” cho mọi JVM.

Kích thước tham chiếu, căn chỉnh và tiêu đề đối tượng phụ thuộc cấu hình JVM. Nếu cần số byte để ra quyết định, hãy đo bằng công cụ phù hợp với môi trường đích thay vì suy ra từ `size()`.

Khi gần giới hạn, cấp phát có thể thất bại vì thiếu heap hoặc giới hạn mảng của JVM. `Integer.MAX_VALUE` không phải lời hứa rằng có thể tạo một `ArrayList` chứa từng ấy phần tử. Không cần chạy thí nghiệm cố chiếm hết bộ nhớ để kiểm chứng một quy tắc sử dụng thường ngày.

### 9.3. Tăng sẵn dung lượng không giải quyết đồng thời hóa

`ArrayList` không tự an toàn khi nhiều luồng cùng sửa cấu trúc. Việc còn nhiều chỗ trống không biến cập nhật kích thước và ghi phần tử thành một giao thức đồng thời đúng.

Nếu chia sẻ danh sách để ghi giữa nhiều luồng, phải có giải pháp đồng bộ hoặc cấu trúc phù hợp với yêu cầu truy cập. Dung lượng là vấn đề lưu trữ và hiệu năng; nó không thay thế quy tắc phối hợp giữa các luồng.

### 9.4. Không suy ra hệ số tăng từ một lần bấm giờ

Một lần đo bằng đồng hồ có thể chịu ảnh hưởng khởi động JVM, biên dịch JIT, tối ưu bỏ công việc không dùng, cấp phát, thu gom rác và tải hệ thống.

Để so sánh có ý nghĩa, phải thống nhất phạm vi đo: có tính constructor, tạo phần tử và dọn dữ liệu hay không; mỗi vòng dùng danh sách mới hay tái sử dụng; dữ liệu có đại diện thực tế hay không. Đặc biệt, không so một trường hợp đã cấp bộ nhớ sẵn với trường hợp còn phải cấp rồi kết luận cấu trúc thứ nhất luôn nhanh hơn theo cùng tỷ lệ.

Bằng chứng toán học giải thích bậc tăng của công việc. Chương trình đếm minh họa xác nhận phép tính trên mô hình. Phép đo hiệu năng thực trả lời một câu hỏi khác trên một JVM và tải xác định.

## 10. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| `new ArrayList<>(100)` có 100 phần tử | Kích thước vẫn 0; tham số dành cho dung lượng ban đầu |
| Có dung lượng thì `set` vào mọi vị trí đều được | `set` chỉ dùng với chỉ số nhỏ hơn `size` |
| Phần tử `null` không tính vào kích thước | Mỗi lần thêm `null` vẫn thêm một phần tử |
| Thêm cuối luôn có chi phí hằng số trong từng lần gọi | Hằng số khấu hao; một lần tăng có thể tuyến tính |
| Khấu hao nghĩa là dữ liệu ngẫu nhiên nên thường nhanh | Phân tích tổng công việc của một chuỗi, không cần giả định ngẫu nhiên |
| Mảng tăng thì mọi đối tượng phần tử được sao chép sâu | Chủ yếu chuyển các tham chiếu; đối tượng được tham chiếu vẫn được chia sẻ |
| Constructor collection luôn độc lập hoàn toàn với nguồn | Cấu trúc độc lập, phần tử có thể là cùng một đối tượng |
| `ensureCapacity` đặt kích thước danh sách | Nó điều chỉnh khả năng chứa, không thêm phần tử |
| `ensureCapacity(k)` bắt buộc dung lượng đúng k | k thể hiện nhu cầu tối thiểu, không phải getter/setter chính xác của mảng |
| `clear` bảo đảm trả ngay toàn bộ bộ nhớ cho hệ điều hành | Xóa nội dung logic; còn phải xét mảng giữ lại và hoạt động GC |
| Thu gọn sau mỗi lần thêm luôn tiết kiệm và nhanh hơn | Có thể phá lợi ích khoảng trống và làm tổng sao chép bậc hai |
| Có dung lượng trước thì thêm ở đầu cũng O(1) | Phần đuôi vẫn cần dịch |
| Tăng dung lượng trước làm danh sách an toàn khi ghi đa luồng | Không thay đổi yêu cầu đồng bộ truy cập |

## 11. Bài tập tự kiểm tra

### Tình huống 1: miền chỉ số

Sau khi tạo `new ArrayList<String>(8)`, chưa thêm phần tử nào, `get(0)` có hợp lệ không? Sau hai lần `add`, `set(2, "C")` có hợp lệ không?

**Giải thích:** Cả hai đều không hợp lệ. Ban đầu `size=0`; sau hai lần thêm `size=2`, chỉ số thay thế hợp lệ là 0 và 1. Muốn có phần tử thứ ba, dùng `add("C")` hoặc `add(2, "C")`.

### Tình huống 2: tổng công việc

Trong mô hình tăng gấp đôi, sau khi thêm 8 phần tử rồi thêm phần tử thứ 9, tổng số lượt sao chép thay đổi ra sao?

**Giải thích:** Sau 8 phần tử đã sao chép 1 + 2 + 4 = 7 lượt. Lần thêm thứ 9 sao chép thêm 8, nên tổng thành 15. Sự tăng đột ngột của một lần không phủ định giới hạn tuyến tính của cả chuỗi.

### Tình huống 3: dự trữ cho lô tiếp theo

Danh sách đang có 700 phần tử, sắp thêm 500. Gọi `ensureCapacity(500)` có diễn đạt đúng nhu cầu của cả đợt không?

**Giải thích:** Không. Tổng nhu cầu là 1.200, nếu không có xóa xen giữa và số đếm đáng tin. Gọi 500 có thể chẳng làm gì vì số phần tử hiện tại đã lớn hơn giá trị đó. Tuy vậy, ngay cả khi không đặt trước, `add` vẫn có khả năng tăng khi cần.

### Tình huống 4: đã cấp quá nhiều

Một danh sách từng chứa 100.000 phần tử, nay còn 100 và sẽ được giữ lâu chỉ để đọc. Có nên tự động gọi `trimToSize` trong mọi lần xóa không?

**Giải thích:** Không cần gắn với mọi lần xóa. Có thể cân nhắc thu gọn một lần sau khi pha giảm dữ liệu hoàn tất, dựa trên vòng đời và nhu cầu dùng lại. Phải tính chi phí sao chép và bộ nhớ tạm; `size=100` tự nó không cho biết dung lượng thực đang giữ.

### Tình huống 5: sao chép nông

Nguồn và bản sao cùng chứa một `StringBuilder`. Xóa tham chiếu khỏi nguồn có xóa phần tử của bản sao không? Thay đổi nội dung `StringBuilder` có thể được bản sao nhìn thấy không?

**Giải thích:** Xóa trong nguồn không xóa phần tử khỏi danh sách bản sao. Thay đổi đối tượng được chia sẻ có thể được thấy từ bản sao. Độc lập của cấu trúc danh sách và độc lập của đối tượng phần tử là hai điều khác nhau.

Khi đọc hoặc viết mã dùng `ArrayList`, hãy xác định rõ đang quan tâm tới **số phần tử**, **chỗ dự trữ**, **chi phí của một lần thao tác**, hay **tổng chi phí của một chuỗi**. Bốn câu hỏi đó giúp chọn constructor đúng, tránh cấp phát thừa và sử dụng kết luận O(1) khấu hao đúng điều kiện.
