# Capacity, load factor và chi phí duyệt HashSet

Một `HashSet` có 100 phần tử không nhất thiết có cùng chi phí duyệt với mọi `HashSet` khác cũng có 100 phần tử. Ngoài số thành viên, còn phải xét kích thước bảng bucket mà nó đang giữ.

Ba khái niệm liên quan nhưng khác nhau:

- **Size:** có bao nhiêu thành viên.
- **Capacity:** bảng nền có bao nhiêu bucket.
- **Load factor:** tham số quyết định mức tải dùng để xét tăng bảng.

Chọn capacity quá nhỏ có thể dẫn tới nhiều lần tăng bảng. Chọn quá lớn hoặc load factor quá thấp có thể tốn bộ nhớ và làm việc duyệt một bảng thưa trở nên đắt. Bài này giải thích cách cân bằng các yếu tố đó, với ví dụ tương thích Java 17.

## 1. Mô hình cần dùng: thành viên và bucket

`HashSet` được hậu thuẫn bởi `HashMap`; các phần tử của set được dùng làm khóa. Bảng bucket giúp chọn một vùng ứng viên khi tìm hoặc thêm khóa.

Một bảng có 8 bucket nhưng chỉ giữ 3 thành viên có thể được hình dung:

~~~text
bucket 0:  rong
bucket 1:  [A]
bucket 2:  rong
bucket 3:  [B] -> [C]
bucket 4:  rong
bucket 5:  rong
bucket 6:  rong
bucket 7:  rong

size = 3
capacity = 8
so bucket khong rong = 2
~~~

Sơ đồ là mô hình giải thích, không phải trạng thái đọc trực tiếp từ một đối tượng Java cụ thể.

### 1.1. Capacity không phải giới hạn số phần tử

Một bucket có thể quản lý nhiều khóa do va chạm. Khi cần, bảng có thể tăng kích thước. Vì vậy, capacity không phải “số phần tử tối đa mà set này được phép chứa”.

Ngược lại, cấp capacity lớn không làm set có sẵn thành viên. `new HashSet<>(1000)` vẫn có size bằng 0 ngay sau khi tạo.

### 1.2. Size không cho biết capacity hiện tại

Hai set có cùng ba thành viên có thể khác lịch sử:

- Một set vừa được tạo rồi thêm ba phần tử.
- Một set được đặt trước bảng rất rộng.
- Một set từng có hàng trăm nghìn thành viên rồi xóa gần hết.

Cùng nội dung hiện tại không có nghĩa cùng cấu trúc lưu trữ đang giữ. Đây là nguyên nhân cần xét capacity khi nói về chi phí duyệt.

[Tài liệu HashSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html) mô tả thời gian duyệt theo cả số thành viên và capacity của map hậu thuẫn.

## 2. Load factor: phân biệt tham số với mức tải thực tế

Gọi n là size, c là capacity của bảng đã cấp.

### 2.1. Mức tải thực tế là n/c

Ta có thể dùng tỷ số:

~~~text
muc tai thuc te = n / c
~~~

Nếu n = 3 và c = 16, mức tải thực tế là 0,1875. Nếu n = 12 và c = 16, nó là 0,75.

Đây không phải tỷ lệ bucket không rỗng. Một bucket chứa nhiều khóa làm size tăng nhưng chỉ đóng góp một bucket không rỗng.

Ví dụ cả ba khóa cùng một bucket, với c = 16:

~~~text
n/c = 3/16
so bucket khong rong / c = 1/16
~~~

Hai tỷ lệ mô tả hai điều khác nhau.

### 2.2. Load factor được cấu hình không luôn bằng n/c

Khi tạo `new HashSet<>(16, 0.75f)`, giá trị 0,75 là tham số dùng để quyết định ngưỡng tăng bảng. Nó không buộc bảng luôn được lấp đúng 75%.

Sau vài lần thêm, sau tăng bảng hoặc sau nhiều lần xóa, n/c có thể nhỏ hơn rất nhiều. Đừng đọc giá trị cấu hình như một phép đo trạng thái hiện tại.

Theo [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), capacity và load factor cùng ảnh hưởng việc tăng bảng và đánh đổi giữa thời gian với không gian.

### 2.3. Ngưỡng thường liên quan capacity × load factor

Gọi α là load factor cấu hình. Trong các trường hợp thông thường, ngưỡng số khóa được xác định gần:

~~~text
threshold = capacity * alpha
~~~

Triển khai cần xử lý chuyển thành số nguyên, làm tròn và giới hạn. Với các giá trị mặc định nhỏ đang xét, ví dụ c = 16, α = 0,75 cho threshold = 12.

Threshold không đếm số bucket không rỗng. Nhiều khóa va chạm cùng một bucket vẫn góp vào size.

### 2.4. Load factor lớn hơn 1 không mặc nhiên là sai kiểu tham số

Không nên học quy tắc “load factor bắt buộc nằm giữa 0 và 1”. Trong triển khai OpenJDK được tham chiếu, tham số dương lớn hơn 1 có thể được chấp nhận; ví dụ 2,0.

Ý nghĩa là ngưỡng theo số khóa có thể lớn hơn số bucket. Cấu trúc vẫn có thể chứa nhiều khóa trong một bucket.

Giá trị 0, âm và NaN bị từ chối trong bản OpenJDK đang xét. Chấp nhận một giá trị không chứng minh đó là lựa chọn tốt cho tải thực tế. Giá trị mặc định 0,75 là điểm bắt đầu thông dụng; chỉ thay đổi khi có yêu cầu và bằng chứng phù hợp.

## 3. Tăng bảng: khi nào và phải trả công việc gì?

Các chi tiết số học trong phần này tham chiếu [HashMap OpenJDK 17, bản jdk-17+35](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/HashMap.java), không là công thức bắt buộc mọi triển khai set phải dùng.

### 3.1. Ví dụ ngưỡng với bảng 16 bucket

Trong một chuỗi thêm khóa khác nhau, không có tình huống va chạm đặc biệt gây tăng sớm, mô hình thông thường là:

| Size sau thêm | Capacity theo mô hình | Threshold theo mô hình |
|---:|---:|---:|
| 1 | 16 | 12 |
| 12 | 16 | 12 |
| 13 | 32 | 24 |
| 24 | 32 | 24 |
| 25 | 64 | 48 |

Một khóa mới làm size vượt threshold thì có thể kích hoạt tăng. Thêm lại một khóa đã có không làm size tăng nên không phải một “thành viên mới” để vượt ngưỡng theo cách đó.

Cần phân biệt “đã tới ngưỡng” với “vượt ngưỡng” trong mô hình này: size 12 vẫn có thể nằm ở bảng 16, size 13 mới qua ngưỡng 12.

### 3.2. Capacity thường được làm tròn theo cách của bảng nền

HashMap trong bản này dùng chiều dài bảng là lũy thừa của 2. Một yêu cầu capacity ban đầu 1000 có thể dẫn tới bảng 1024 khi cấp phát, không phải một mảng bucket dài đúng 1000.

Vì thế, tham số constructor, capacity đã được làm tròn và threshold là ba giá trị cần phân biệt. Không suy ra capacity thật chỉ bằng cách đọc lại con số từng truyền cho constructor.

Bảng còn được cấp lười: tạo set rỗng không đồng nghĩa ngay lúc đó đã cấp toàn bộ mảng bucket. Chương trình không có getter công khai của `HashSet` để đọc capacity.

### 3.3. Tăng bảng có cấp phát và phân bố lại

Khi bảng tăng, cần vùng bucket mới và phải tổ chức lại vị trí của các mục đang có. Một số khóa chuyển sang bucket khác vì mặt nạ chỉ số đã thay đổi.

Do vậy, thêm một phần tử có thể rẻ trong lần thường nhưng đắt hơn khi phải tăng bảng. Phân tích chuỗi thao tác phải tính phần việc tăng, rồi mới nói về chi phí kỳ vọng/khấu hao.

Không được dùng kết luận O(1) cho thêm theo nghĩa “mọi lần add đều không cấp phát và không xử lý các mục cũ”.

### 3.4. Ngưỡng size không phải lý do tăng duy nhất trong mọi đường đi

Khi có nhiều va chạm trong một bucket và bảng còn nhỏ, bản OpenJDK này có thể tăng bảng như một phần của cơ chế xử lý va chạm, trước khi lời giải thích đơn giản bằng size×load factor mô tả hết tình huống.

Vì vậy, bảng số ở trên và chương trình mô phỏng chỉ trình bày đường đi tăng thông thường. Không biến nó thành một kiểm thử rằng mọi tập khóa đều phải có cùng capacity sau từng lần thêm.

Tính toán đặt trước dung lượng giúp giảm tăng theo ngưỡng size; nó không là một bảo đảm vô điều kiện cho mọi hành vi nội bộ.

## 4. Vì sao duyệt HashSet phụ thuộc cả size và capacity?

### 4.1. Tìm một phần tử và duyệt mọi phần tử là hai công việc khác nhau

Một lần `contains(key)` tính hash và chọn bucket ứng viên. Nó không cần đi qua toàn bộ bảng nếu khóa và cấu trúc đang được quản lý bình thường.

Một iterator phải tìm mọi thành viên. Trong mô hình bảng băm, nó đi qua các vị trí bucket và các mục nằm trong những bucket không rỗng.

Có thể tách công việc tổng quát thành:

~~~text
cong viec di qua bang bucket     ~ c
cong viec tra/xu ly cac thanh vien ~ n

tong ~ c + n
~~~

Do đó, chi phí duyệt thường được biểu diễn là **O(c + n)**, chưa tính phần việc ứng dụng làm với từng phần tử.

### 4.2. Ba lần chạy thân for-each không có nghĩa chỉ ba bước bên trong

Nếu set chứa đúng ba phần tử, thân vòng `for-each` được gọi ba lần. Nhưng để tìm các phần tử tiếp theo, iterator có thể phải bỏ qua những vùng bucket rỗng giữa chúng.

Hai set có cùng size = 3 và cùng tổng giá trị sẽ cho cùng số lần chạy thân vòng lặp. Điều đó không đo được phần việc tìm các mục trong bảng nền.

Chương trình ở phần thực hành in hai nhóm riêng:

- Số phần tử do iterator thật trả ra.
- Số bucket và phần tử được quét trong một mô hình cố định có chủ đích.

Không cộng các con số đó thành một phép đo thời gian của JVM.

### 4.3. Khi c cùng bậc với n, O(c+n) có thể rút thành O(n)

Nếu bảng tăng hợp lý theo dữ liệu và chưa bị xóa thưa đi nhiều, capacity có thể cùng bậc với số thành viên. Khi ấy cách nói duyệt tuyến tính theo n là hợp lý trong điều kiện đó.

Nhưng nếu c lớn hơn n rất nhiều, bỏ c khỏi phân tích làm mất yếu tố quan trọng. Điều này thường xảy ra do:

- Đặt trước capacity vượt xa số thành viên thực tế.
- Chọn load factor rất thấp.
- Set từng lớn rồi bị xóa phần lớn dữ liệu.
- Ước lượng theo tổng bản ghi đầu vào trong khi chỉ có ít khóa duy nhất.

Không cần một benchmark mới để nhận ra rằng “duyệt luôn chỉ phụ thuộc size” là phát biểu thiếu điều kiện; hợp đồng tài liệu đã nêu cả capacity.

### 4.4. Không biến c+n thành một số lệnh hoặc số nano giây chính xác

Mô hình cho biết các đại lượng nào ảnh hưởng lượng công việc. Thời gian thực còn phụ thuộc bố trí bộ nhớ, loại khóa, bộ gom rác, JIT và công việc trong thân vòng lặp.

Triển khai cũng có đường đi riêng cho những trường hợp đặc biệt, như kết thúc nhanh khi không có phần tử. Không nên hiểu c+n là mệnh lệnh rằng mọi set rỗng đều bắt buộc đọc từng bucket.

Điểm cần giữ là: khi bảng rộng còn có dữ liệu, các bucket rỗng có thể tạo chi phí mà việc chỉ đếm số phần tử trả ra không thể hiện.

## 5. Chọn capacity ban đầu theo số thành viên dự kiến

### 5.1. Một con số truyền vào không tự là expected size

Nếu dự kiến giữ 1000 thành viên duy nhất, `new HashSet<>(1000)` không có nghĩa ngưỡng tăng sẽ bằng 1000.

Theo mô hình bản OpenJDK đang xét:

~~~text
yeu cau ban dau = 1000
capacity lam tron = 1024
load factor = 0.75
threshold = 768
~~~

Nếu tiếp tục thêm tới 1000 khóa khác nhau, ngưỡng theo size sẽ bị vượt trước khi đủ 1000.

### 5.2. Ước lượng để giảm tăng theo ngưỡng size

Một phép tính tham khảo với số nhỏ, load factor α và số thành viên dự kiến N là:

~~~text
yeu cau capacity ban dau gan ceil(N / alpha)
~~~

Với N = 1000, α = 0,75:

~~~text
ceil(1000 / 0.75) = 1334

lam tron ve luy thua 2 -> 2048
threshold -> 1536
~~~

Điều này giải thích vì sao số bucket thực tế có thể lớn hơn đáng kể số thành viên dự kiến. Nó không có nghĩa cần luôn cấp dư theo một hệ số cố định trong mọi bài toán.

Nếu xây một helper dùng cho đầu vào lớn, phải xử lý phạm vi số nguyên, chuyển kiểu và giới hạn bộ nhớ. Đoạn tính trong chương trình chỉ dùng ví dụ 1000 đã biết, không được trình bày như một hàm sizing hoàn chỉnh cho mọi giá trị.

Ngoài ra, những đường xử lý va chạm đặc biệt đã nêu có thể làm điều kiện tăng phức tạp hơn công thức size. Mục tiêu ở đây là ước lượng có căn cứ, không hứa kiểm soát tuyệt đối nội bộ.

### 5.3. Dự kiến số khóa duy nhất, không chỉ số bản ghi

Nếu một nguồn có một triệu bản ghi nhưng chỉ có vài trăm mã khác nhau, capacity của set phục vụ vài trăm thành viên, không phải một triệu lần gọi add.

Ước lượng theo mọi bản ghi có thể làm bảng thưa quá mức. Hãy dùng số thành viên duy nhất dự kiến nếu biết, hoặc để set tăng theo dữ liệu thực tế rồi đánh giá.

Constructor nhận collection cũng phải ước lượng trước khi hoàn tất loại trùng. Trong [HashSet OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/HashSet.java), việc khởi tạo dựa trên kích thước collection nguồn có thể tạo một bảng rộng hơn nhiều so với số khóa duy nhất cuối cùng nếu đầu vào rất nhiều trùng.

Vì thế, “truyền toàn bộ nguồn vào constructor” thuận tiện về cú pháp nhưng không thay thế việc xét phân bố dữ liệu khi bộ nhớ và các lượt duyệt sau đó là vấn đề.

### 5.4. Không giảm load factor theo thói quen

Load factor thấp hơn thường thúc đẩy dùng nhiều bucket hơn cho cùng số khóa. Điều đó có thể giảm một số va chạm khi hash phân bố phù hợp, nhưng tăng vùng bảng và có thể làm duyệt thưa hơn.

Load factor cao hơn có thể tiết kiệm bucket nhưng để nhiều khóa cùng vùng hơn và làm phần tìm kiếm khó hơn. Hai khóa có cùng mã băm không tự tách ra chỉ vì bảng rộng hơn.

Không có quy tắc “load factor càng thấp thì mọi thao tác càng nhanh”. Hãy xét tỷ lệ tìm kiếm, thêm/xóa, duyệt toàn bộ và ngân sách bộ nhớ.

## 6. Sau khi xóa nhiều phần tử, capacity có tự nhỏ lại không?

### 6.1. Xóa thành viên không có nghĩa thu bảng theo size mới

Ở bản OpenJDK đang tham chiếu, việc xóa khóa thông thường không tự giảm chiều dài bảng bucket theo từng lần xóa.

Một set từng có nhiều khóa rồi chỉ còn ba khóa có thể vẫn giữ bảng lớn. Nội dung đã nhỏ lại, nhưng lịch sử tăng bảng vẫn ảnh hưởng bộ nhớ và những lần duyệt tiếp theo.

Việc một bucket có thể đổi hình thức tổ chức bên trong khi số mục thay đổi không đồng nghĩa toàn bảng được thu nhỏ.

### 6.2. clear làm rỗng nhưng không hứa trả lại mảng bucket

Trong bản này, `HashSet.clear` dùng việc clear map: xóa các liên kết mục khỏi bảng và đặt số thành viên về 0, còn mảng bucket vẫn có thể được giữ để tái sử dụng.

Không kết luận rằng size về 0 thì capacity cũng về 0, hoặc bộ nhớ đã được trả ngay cho hệ điều hành. Thời điểm thu hồi còn phụ thuộc tham chiếu và JVM.

Set rỗng có thể được nhận diện nhanh khi duyệt; điều đó không chứng minh mảng nền đã biến mất. Khi thêm lại một ít thành viên, bảng vẫn có thể ở trạng thái rất rộng so với nội dung.

### 6.3. Tạo lại set có thể phù hợp ở một ranh giới vòng đời

Nếu dữ liệu đã giảm ổn định và set sẽ được giữ lâu, có thể cân nhắc:

~~~java
Set<Integer> compacted = new HashSet<>(existing);
~~~

Việc này tạo một cấu trúc set khác từ các thành viên hiện có, không giữ nguyên lịch sử capacity của bảng cũ. Với set nhỏ trong bản đang xét, cách khởi tạo dùng lại chính sách mặc định phù hợp với kích thước nguồn.

Nhưng quá trình tạo lại không miễn phí:

- Phải duyệt set cũ, nên phần đọc nguồn có thể vẫn chịu chi phí c+n của bảng rộng.
- Cần bộ nhớ cho set mới và các mục mới trong lúc set cũ còn tồn tại.
- Các phần tử được chia sẻ bằng tham chiếu, không được sao chép sâu.
- Những nơi còn giữ tham chiếu tới set cũ không tự chuyển sang set mới.

Nếu set sắp lớn lại ngay, tạo lại thường xuyên có thể chỉ làm thêm công việc cấp phát. Hãy chọn theo vòng đời, không rebuild sau mọi lần remove.

`HashSet` không có phương thức công khai `trimToSize()` như `ArrayList`. Không dùng một API của collection khác để suy ra khả năng thu gọn của set.

## 7. Chương trình hoàn chỉnh: số phần tử trả ra và mô hình quét bảng

Chương trình có ba loại minh chứng tách biệt:

1. Set thật: kiểm tra thành viên, số phần tử iterator trả ra và tổng.
2. Mô hình bảng cố định: đếm rõ bucket và phần tử được quét.
3. Phép tính tăng/sizing: minh họa các ngưỡng nhỏ theo điều kiện đã nêu.

Không có reflection, không đọc capacity thật và không đo thời gian.

### 7.1. Mã nguồn

Lưu thành `HashSetCapacityDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class HashSetCapacityDemo {
    record Returned(int elements, long sum) {}
    record ModelScan(int buckets, int elements, long sum) {}

    static Returned returnedByIterator(Set<Integer> values) {
        int elements = 0;
        long sum = 0;
        for (int value : values) {
            elements++;
            sum += value;
        }
        return new Returned(elements, sum);
    }

    // Mo hinh bang co dinh, khong phai noi bo HashSet hay benchmark.
    static ModelScan scanFixedBuckets(int capacity, List<Integer> input) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("positive capacity required");
        }
        List<List<Integer>> buckets = new ArrayList<>(capacity);
        for (int index = 0; index < capacity; index++) {
            buckets.add(new ArrayList<>());
        }
        for (int value : input) {
            List<Integer> bucket = buckets.get(Math.floorMod(value, capacity));
            if (!bucket.contains(value)) {
                bucket.add(value);
            }
        }
        int bucketVisits = 0;
        int elementVisits = 0;
        long sum = 0;
        for (List<Integer> bucket : buckets) {
            bucketVisits++;
            for (int value : bucket) {
                elementVisits++;
                sum += value;
            }
        }
        return new ModelScan(bucketVisits, elementVisits, sum);
    }

    // Chi dung cac so nho de minh hoa lam tron ve luy thua cua 2.
    static int demoRoundedCapacity(int requested) {
        if (requested < 1 || requested > 1_048_576) {
            throw new IllegalArgumentException("outside demo range");
        }
        int capacity = 1;
        while (capacity < requested) {
            capacity *= 2;
        }
        return capacity;
    }

    static void showInvalid(String name, Runnable constructor) {
        try {
            constructor.run();
            throw new AssertionError("expected IllegalArgumentException");
        } catch (IllegalArgumentException exception) {
            System.out.println(name + ": IllegalArgumentException");
        }
    }

    public static void main(String[] args) {
        List<Integer> keys = List.of(1, 2, 3);
        Set<Integer> small = new HashSet<>(16);
        Set<Integer> wide = new HashSet<>(1024);
        small.addAll(keys);
        wide.addAll(keys);
        System.out.println("same members: " + small.equals(wide));
        System.out.println("actual small returned: " + returnedByIterator(small));
        System.out.println("actual wide returned: " + returnedByIterator(wide));
        System.out.println("model capacity16: " + scanFixedBuckets(16, keys));
        System.out.println("model capacity1024: " + scanFixedBuckets(1024, keys));
        System.out.printf("duplicate add: returned=%s, size=%d%n",
                small.add(2), small.size());

        int capacity = 16;
        int threshold = 12;
        for (int size = 1; size <= 25; size++) {
            if (size > threshold) {
                capacity *= 2;
                threshold = (int) (capacity * 0.75f);
            }
            if (size == 1 || size == 12 || size == 13 || size == 24 || size == 25) {
                System.out.printf("growth model: size=%d, capacity=%d, threshold=%d%n",
                        size, capacity, threshold);
            }
        }

        int expected = 1000;
        int rawRequested = expected;
        int plannedRequested = (int) Math.ceil(expected / 0.75d);
        int rawCapacity = demoRoundedCapacity(rawRequested);
        int plannedCapacity = demoRoundedCapacity(plannedRequested);
        System.out.printf("request1000 model: capacity=%d, threshold=%d%n",
                rawCapacity, (int) (rawCapacity * 0.75f));
        System.out.printf("plan1000 model: requested=%d, capacity=%d, threshold=%d%n",
                plannedRequested, plannedCapacity, (int) (plannedCapacity * 0.75f));

        Set<Integer> sparse = new HashSet<>();
        for (int value = 0; value < 1000; value++) {
            sparse.add(value);
        }
        for (int value = 3; value < 1000; value++) {
            sparse.remove(value);
        }
        Set<Integer> rebuilt = new HashSet<>(sparse);
        System.out.println("after removals: " + returnedByIterator(sparse));
        System.out.printf("rebuilt: sameMembers=%s, returned=%s%n",
                sparse.equals(rebuilt), returnedByIterator(rebuilt));
        sparse.clear();
        System.out.println("after clear: size=" + sparse.size());

        showInvalid("negative capacity", () -> new HashSet<>(-1));
        showInvalid("zero load factor", () -> new HashSet<>(16, 0.0f));
        showInvalid("NaN load factor", () -> new HashSet<>(16, Float.NaN));
        Set<Integer> greaterThanOne = new HashSet<>(16, 2.0f);
        System.out.println("load factor 2.0 accepted: size=" + greaterThanOne.size());
        System.out.println("capacity zero accepted: size=" + new HashSet<Integer>(0).size());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 HashSetCapacityDemo.java
java HashSetCapacityDemo
~~~

### 7.2. Kết quả stdout

~~~text
same members: true
actual small returned: Returned[elements=3, sum=6]
actual wide returned: Returned[elements=3, sum=6]
model capacity16: ModelScan[buckets=16, elements=3, sum=6]
model capacity1024: ModelScan[buckets=1024, elements=3, sum=6]
duplicate add: returned=false, size=3
growth model: size=1, capacity=16, threshold=12
growth model: size=12, capacity=16, threshold=12
growth model: size=13, capacity=32, threshold=24
growth model: size=24, capacity=32, threshold=24
growth model: size=25, capacity=64, threshold=48
request1000 model: capacity=1024, threshold=768
plan1000 model: requested=1334, capacity=2048, threshold=1536
after removals: Returned[elements=3, sum=3]
rebuilt: sameMembers=true, returned=Returned[elements=3, sum=3]
after clear: size=0
negative capacity: IllegalArgumentException
zero load factor: IllegalArgumentException
NaN load factor: IllegalArgumentException
load factor 2.0 accepted: size=0
capacity zero accepted: size=0
~~~

### 7.3. Giải thích kết quả

Hai set thật có cùng các thành viên 1, 2, 3. Iterator trả đúng ba phần tử, tổng là 6, dù các yêu cầu capacity ban đầu khác nhau.

Mô hình cố định vẫn xử lý ba phần tử nhưng quét 16 hoặc 1024 bucket. Đây là cách làm lộ phần c trong công thức, không phải một tuyên bố rằng thời gian thực chênh đúng 64 lần.

`scanFixedBuckets` dùng các danh sách Java để biểu diễn bucket và một phép chia lấy dư đơn giản. Nó không tái hiện toàn bộ cách cấp phát, hash, xử lý va chạm, cây hay tối ưu iterator của HashMap. Số đối tượng và số byte trong mô hình không được dùng để ước lượng bộ nhớ thật của HashSet.

Thêm lại 2 trả false và giữ size = 3. Điều đó khác một lần thêm khóa mới làm size tiến qua threshold.

Nhóm growth model chỉ dùng chuỗi size và điều kiện ngưỡng thông thường; nó không quan sát một HashSet để đếm số lần resize. Các dòng 12→13 và 24→25 kiểm tra phép tính trong bảng giải thích.

Hai dòng request1000 và plan1000 phân biệt số yêu cầu constructor với capacity làm tròn và threshold. Hàm làm tròn được giới hạn cố ý cho các số nhỏ của bài học, không là API sizing sản xuất.

Sau khi xóa 997 trong số 1000 khóa, set còn 0, 1, 2 nên số phần tử là 3 và tổng là 3. Bản sao mới có cùng thành viên; chương trình không suy từ equality ra rằng hai cấu trúc có cùng capacity.

Các kiểm tra constructor chứng minh capacity âm, load factor 0 và NaN bị từ chối, còn 2,0 được chấp nhận. Capacity 0 cũng hợp lệ; nó tạo một set rỗng có thể tiếp tục thêm, không là yêu cầu cấm mọi phần tử về sau.

### 7.4. Kết quả này chưa phải benchmark

Không có giá trị nano giây hoặc số byte nào được đo. Các bộ đếm mô hình là công việc đã được định nghĩa rõ trong mã, còn set thật chỉ được quan sát qua API công khai.

Muốn so sánh hiệu năng thực, phải chuẩn bị đúng kiểu dữ liệu, trạng thái đầy/thưa, số lần duyệt và phạm vi tính cấp phát. Một phép đo chỉ chạy một vòng có thể chịu ảnh hưởng khởi động JVM, JIT, bộ gom rác và tải máy.

Đặc biệt, đừng đếm số lần chạy thân for-each rồi coi đó là toàn bộ công việc của iterator; đây chính là điều bài muốn phân biệt.

## 8. Khi phần lớn công việc là duyệt, có lựa chọn nào khác?

### 8.1. LinkedHashSet đi qua chuỗi các mục

`LinkedHashSet` duy trì liên kết giữa các mục để có thứ tự duyệt xác định. Tài liệu [LinkedHashSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html) mô tả thời gian duyệt tỷ lệ với số phần tử, không phụ thuộc capacity theo cách duyệt bảng của HashSet.

Điều này có thể hữu ích nếu ứng dụng vừa cần tính duy nhất vừa thường xuyên duyệt một bảng thưa. Tuy nhiên, nó cần thêm thông tin liên kết và công việc bảo trì các liên kết; không có kết luận rằng nó luôn tốt hơn về mọi khía cạnh.

Nếu không cần thứ tự, vẫn có thể cân nhắc nó theo mẫu truy cập, nhưng cần đo khi hiệu năng thực là tiêu chí quyết định.

### 8.2. Sau pha loại trùng, một List có thể đủ cho pha đọc

Nếu chỉ cần set để lọc trùng lúc xây dữ liệu, rồi nhiều lần duyệt mà không cần kiểm tra thành viên nữa, có thể tạo một danh sách kết quả tại ranh giới giữa hai pha.

Việc chuyển cần một lần đọc set hiện tại và bộ nhớ cho danh sách. Những lần duyệt danh sách về sau không cần quét bảng bucket của set.

Cách này chỉ phù hợp nếu hợp đồng cho phép một bản chụp độc lập về cấu trúc. Nếu set nguồn tiếp tục thay đổi, danh sách không tự cập nhật.

### 8.3. Giữ HashSet nhưng chọn sizing hợp lý cũng có thể đủ

Không cần đổi cấu trúc chỉ vì đọc thấy công thức c+n. Nếu capacity và size có tỷ lệ hợp lý, lượng công việc có thể phù hợp với mục tiêu.

Thay đổi đơn giản như bỏ một con số pre-size quá lớn, ước lượng theo số khóa duy nhất hoặc dựng lại ở đúng vòng đời có thể giải quyết vấn đề.

Hãy chọn theo phần việc chiếm ưu thế: tìm thành viên, xây dữ liệu, xóa nhiều, hay duyệt lặp. Một cấu hình tối ưu cho một pha chưa chắc tối ưu cho pha khác.

## 9. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Capacity là số phần tử hiện có | Đó là số bucket của bảng khi đã cấp |
| Capacity là số bucket không rỗng | Va chạm khiến nhiều khóa cùng một bucket |
| Load factor 0,75 nghĩa là luôn có 75% bucket được dùng | Đây là tham số ngưỡng, không phải tỷ lệ bucket không rỗng |
| Actual load luôn bằng load factor cấu hình | n/c thay đổi theo thêm, xóa và resize |
| new HashSet(1000) giữ được 1000 khóa trước mọi lần tăng | Còn làm tròn bảng, threshold và đường xử lý va chạm |
| Load factor bắt buộc nhỏ hơn hoặc bằng 1 | Giá trị dương lớn hơn 1 có thể hợp lệ |
| Hạ load factor luôn làm mọi thao tác nhanh hơn | Có thể tăng bộ nhớ và chi phí duyệt bảng thưa |
| Chỉ cần biết size để biết chi phí duyệt | Cần xét cả capacity |
| Thân for-each chạy n lần nên iterator chỉ làm n bước | Còn phần tìm mục qua các bucket |
| Xóa gần hết thì bảng tự nhỏ ngay | Bản OpenJDK đang xét không tự thu bảng theo mỗi remove |
| Clear bảo đảm capacity về 0 | Làm rỗng nội dung không đồng nghĩa bỏ mảng bucket |
| Rebuild không tốn gì vì set mới nhỏ | Vẫn phải đọc nguồn và cấp cấu trúc mới |
| Bản sao set độc lập luôn có các đối tượng phần tử độc lập | Cấu trúc riêng, tham chiếu phần tử có thể chia sẻ |
| Công thức c+n cho được tỷ lệ tốc độ chính xác | Nó mô tả bậc công việc, không thay thế phép đo thời gian |

## 10. Bài tập tự kiểm tra

### Bài 1: tải thực tế

Size = 20, capacity = 64, load factor cấu hình = 0,75. Mức tải n/c có phải 0,75 không?

**Giải thích:** Không; 20/64 = 0,3125. Giá trị cấu hình là tham số ngưỡng, không tự bằng tỷ số hiện tại.

### Bài 2: ngưỡng thông thường

Capacity = 32, load factor = 0,75. Threshold theo mô hình thông thường là bao nhiêu? Size 24 và 25 khác nhau ra sao?

**Giải thích:** Threshold = 24. Size 24 chưa vượt ngưỡng; thêm khóa mới thành 25 vượt ngưỡng và có thể gây tăng theo đường đi đang xét.

### Bài 3: cùng size nhưng khác capacity

Hai set đều có 10 thành viên, một bảng 32 bucket, một bảng 65.536 bucket. Vì sao không thể chỉ dùng n = 10 để giải thích mọi công việc duyệt?

**Giải thích:** Iterator còn phải tìm các mục qua bảng. Khi c lớn hơn n rất nhiều, phần c có thể chiếm ưu thế. Không suy ra một tỷ lệ thời gian chính xác chỉ từ hai con số.

### Bài 4: đầu vào nhiều trùng

Có 100.000 dòng nhưng chỉ 100 mã khác nhau. Khi tính capacity cho một set mã, nên ưu tiên dự kiến 100.000 hay 100 thành viên nếu đã biết rõ dữ liệu?

**Giải thích:** Số thành viên duy nhất dự kiến là 100. Số dòng ảnh hưởng công việc đọc/xử lý đầu vào nhưng không bắt buộc set cần giữ 100.000 khóa khác nhau.

### Bài 5: thu bảng sau xóa

Một set từng rất lớn, nay còn ít khóa và sẽ được đọc nhiều lần trong thời gian dài. Tạo set mới từ các khóa hiện tại có thể có lợi nhưng cần tính gì?

**Giải thích:** Tính chi phí duyệt bảng cũ, cấp set mới, bộ nhớ hai cấu trúc cùng tồn tại, các tham chiếu bên ngoài tới set cũ và việc dữ liệu có sắp tăng lại không.

### Bài 6: kết quả của mô hình

Mô hình quét 1024 bucket và trả 3 phần tử. Có được kết luận một HashSet thật cũng có đúng 1027 lệnh máy cho lần duyệt không?

**Giải thích:** Không. Bộ đếm biểu diễn hai loại công việc trừu tượng; JVM và triển khai có nhiều bước và tối ưu khác. Nó giúp thấy yếu tố capacity, không phải đếm lệnh máy.

Capacity và load factor quyết định cách HashSet dành không gian và tăng bảng; số thành viên quyết định lượng dữ liệu logic. Khi phân tích các lượt duyệt, hãy giữ cả hai đại lượng c và n, rồi đối chiếu với vòng đời và mẫu truy cập của ứng dụng.
