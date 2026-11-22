# Capacity, load factor, ngưỡng mở rộng và rehash

## 1. Vì sao HashMap cần một chính sách mở rộng?

Một `HashMap<K, V>` lưu các ánh xạ khóa–giá trị trên một bảng băm. Bảng có các vị trí đầu mối gọi là **bucket**. Từ mã băm của khóa, hiện thực xác định bucket và tìm ánh xạ tương ứng trong đó.

Nhiều khóa có thể đi vào cùng một bucket. Vì thế bảng băm không phải một mảng trong đó “mỗi ô chứa đúng một ánh xạ, đầy ô mới được thêm tiếp”. Một bucket có thể quản lý nhiều ánh xạ; ngược lại, một số bucket có thể rỗng.

Khi số ánh xạ tăng, giữ nguyên một bảng nhỏ có thể làm nhiều khóa tập trung hơn vào các bucket và tăng công việc tra cứu. Mở rộng bảng giúp có thêm không gian phân bố, nhưng phải cấp phát và tổ chức lại dữ liệu. `HashMap` cần cân bằng hai chi phí đó.

Bốn khái niệm của bài liên hệ như sau:

```text
Số ánh xạ hiện có: size
             ↓ so với
Ngưỡng mở rộng: threshold
             ↑ chịu ảnh hưởng bởi
Số bucket: capacity × chính sách load factor
             ↓ khi cần mở rộng
Bảng lớn hơn + phân bố lại ánh xạ
             = resize / rehash theo ngữ cảnh
```

Bài tách rõ hai tầng: **hợp đồng API HashMap** và **chi tiết hiện thực OpenJDK**. Các con số bucket, trường nội bộ và thuật toán chia bucket được giải thích theo mã nguồn OpenJDK 17u đã đối chiếu. Các chương trình được biên dịch với mức tương thích Java 17 và chạy kiểm chứng trên JDK 24.0.2; phép quan sát nội bộ được ghi rõ để không nhầm thành API công khai ổn định cho mọi Java runtime.

## 2. Bốn đại lượng phải phân biệt

| Đại lượng | Ý nghĩa | Có thể đọc trực tiếp bằng API công khai không? |
|---|---|---|
| `size` | Số ánh xạ hiện đang có | Có: `map.size()` |
| `capacity` | Số bucket của bảng đã cấp phát | Không có `HashMap.capacity()` công khai |
| `load factor` | Tham số chính sách ảnh hưởng mức tải trước khi mở rộng | Chọn khi dựng map; không có getter/setter công khai tương ứng |
| `threshold` | Ngưỡng kích thước mà hiện thực dùng để quyết định mở rộng | Không có getter công khai |

### Capacity không phải số phần tử tối đa

Một bảng có capacity `16` không có nghĩa map chỉ lưu tối đa `16` ánh xạ. Khi chính sách yêu cầu, nó có thể mở rộng và tiếp tục chứa thêm. Ngay cả khi số ánh xạ vượt số bucket, mô hình nhiều ánh xạ trong một bucket vẫn có thể biểu diễn dữ liệu.

Tương tự, `new HashMap<>(100)` không tạo sẵn `100` ánh xạ. Map mới có `size() == 0`. Tham số này liên quan dung lượng ban đầu, không phải việc thêm khóa, cũng không phải một giới hạn cứng chặn lần thêm thứ `101`.

### Size thay đổi theo khóa mới, không theo số lần gọi put

Một triệu lần `put` vào cùng một khóa logic có thể vẫn chỉ để lại một ánh xạ. Nếu mỗi lần chỉ thay giá trị của khóa đã có, kích thước không tăng.

Khi tính dung lượng, điều cần ước lượng là số khóa logic khác nhau cùng tồn tại ở một thời điểm, thường là mức đỉnh dự kiến. Số yêu cầu xử lý tích lũy hay số lần gọi phương thức không tự là số bucket cần có.

## 3. Load factor là chính sách tải, không phải phần trăm bucket đang có dữ liệu

Gọi:

- `n`: số ánh xạ hiện có.
- `m`: số bucket đã cấp phát.
- `α = n / m`: mức tải hiện tại, khi bảng đã tồn tại.
- `f`: load factor được chọn.

`α` là trạng thái hiện tại; `f` là một tham số chính sách. Chúng không phải hai tên của cùng một đại lượng.

Với `n = 12`, `m = 16`, ta có mức tải trung bình `α = 0.75`. Điều đó **không khẳng định đúng 12 bucket có dữ liệu**. Nếu nhiều khóa va chạm, số bucket không rỗng có thể ít hơn.

Load factor mặc định của `HashMap` là `0.75f`. Nó cân bằng chi phí bộ nhớ của bảng với công việc tìm trong các bucket trong nhiều tình huống thông thường.

| Chọn load factor | Xu hướng đánh đổi |
|---|---|
| Thấp hơn | Mở rộng với tải thấp hơn; thường cần nhiều bucket hơn cho cùng số ánh xạ |
| Cao hơn | Có thể dùng ít bucket hơn; trung bình có thể tăng công việc xử lý trong bucket |
| Mặc định `0.75f` | Điểm bắt đầu hợp lý khi chưa có dữ liệu đo cần thay đổi |

Đây là xu hướng, không phải cam kết một lựa chọn luôn nhanh hơn. Hàm băm, kiểu khóa, mẫu truy cập, tần suất duyệt, bộ nhớ và chi phí của giá trị đều có thể ảnh hưởng.

Load factor không bị giới hạn về mặt ý nghĩa ở khoảng “từ 0 đến 1” như phần trăm ô được lấp. Một giá trị lớn hơn `1` không có nghĩa map không thể hoạt động, vì một bucket có thể có nhiều ánh xạ. Tuy nhiên, không nên chọn một hệ số cực đoan chỉ để trì hoãn mở rộng mà bỏ qua chi phí tra cứu.

Constructor từ chối dung lượng âm và load factor không dương; mã nguồn OpenJDK cũng kiểm tra `NaN`. Capacity ban đầu bằng `0` được phép, nhưng không làm map thành một cấu trúc không thể thêm dữ liệu. Cấu hình rất nhỏ và các giá trị biên cần theo đúng cách làm tròn của hiện thực.

## 4. Ngưỡng mở rộng: size bằng ngưỡng khác size vượt ngưỡng

Mô hình thường dùng là:

```text
threshold ≈ capacity × load factor
```

Với dung lượng là lũy thừa của hai và hệ số mặc định trong các ví dụ thông thường, các ngưỡng là:

| Capacity đã cấp phát | Load factor | Threshold |
|---:|---:|---:|
| 4 | 0.75 | 3 |
| 8 | 0.75 | 6 |
| 16 | 0.75 | 12 |
| 32 | 0.75 | 24 |
| 64 | 0.75 | 48 |

Xét đường gọi `put` thông thường của OpenJDK, không có chính sách va chạm khác kích hoạt mở rộng sớm và chưa ở giới hạn dung lượng: sau khi thêm **khóa mới**, hiện thực tăng `size` rồi kiểm tra việc vượt ngưỡng.

Với capacity `16`, threshold `12`:

- Sau khóa thứ `12`: `size == 12`, chưa vượt ngưỡng này.
- Sau khóa thứ `13`: `size == 13 > 12`, cần mở rộng theo đường kiểm tra tải.
- Ghi lại một khóa đã có chỉ thay giá trị, không tăng `size` để đi theo đường thêm mới đó.

Đừng dùng `>=` thay cho `>` khi dự đoán chính chuỗi `put` của ví dụ. Đồng thời, đừng biến mô hình thành một giả định rằng mọi phương thức khác đều kiểm tra ở cùng đúng một vị trí trong mã nguồn: thao tác hàng loạt và các phương thức tính/cập nhật có thể đi qua những đường hiện thực khác.

### Vì sao dùng dấu xấp xỉ thay vì công thức tuyệt đối cho mọi cấu hình?

Threshold là một số nguyên. Hiện thực có các bước làm tròn, có thể tăng gấp đôi threshold cũ trong một đường mở rộng, và có xử lý riêng ở giới hạn.

Ví dụ, với load factor `0.6f`, một bảng `16` có thể có threshold ban đầu là `9`. Khi mở rộng lên `32` theo đường nhân đôi threshold cũ, ngưỡng là `18`, không phải cứ tính lại `floor(32 × 0.6)` rồi bắt buộc nhận `19`.

Vì vậy:

- Dùng tích `capacity × load factor` để hiểu chính sách và lập kế hoạch thông thường.
- Dùng các giá trị đã xác định của cấu hình mặc định khi giải bài cụ thể.
- Khi cần số nội bộ chính xác cho một cấu hình tùy biến, đối chiếu đúng hiện thực thay vì suy mọi trường hợp từ một công thức rút gọn.

## 5. Initial capacity, làm tròn và cấp phát trễ

OpenJDK tổ chức chiều dài bảng băm theo lũy thừa của hai, trong phạm vi giới hạn của hiện thực. Tham số constructor được chuyển thành dung lượng mục tiêu phù hợp.

Ví dụ các dung lượng mục tiêu thường gặp:

| Đối số initialCapacity | Dung lượng mục tiêu theo cách làm tròn OpenJDK |
|---:|---:|
| 4 | 4 |
| 13 | 16 |
| 16 | 16 |
| 17 | 32 |
| 100 | 128 |
| 134 | 256 |

Điều này không nói bảng đã được cấp phát ngay ở constructor. Trong các constructor quan sát ở OpenJDK, việc cấp phát mảng bucket được trì hoãn đến khi cần chèn dữ liệu.

Với `new HashMap<>(17)`:

```text
Vừa dựng:
    size = 0
    chưa có mảng bucket
    có thông tin dung lượng mục tiêu 32

Sau lần put đầu:
    có bảng dài 32
    threshold thông thường = 24 với hệ số mặc định
```

### Trường nội bộ tên threshold có thể giữ thông tin khác trước cấp phát

Trước khi bảng tồn tại, OpenJDK có thể dùng trường `threshold` để giữ dung lượng mục tiêu. Vì vậy đọc thấy `thresholdField = 32` khi `tableLength = 0` không có nghĩa một bảng rỗng đang cho phép `32` ánh xạ trước khi mở rộng.

Sau khi cấp phát bảng, trường này mới mang vai trò ngưỡng phù hợp với trạng thái bảng trong các ví dụ đang xét.

Đây là một lý do không nên biến các trường private thành giao diện nghiệp vụ. Tên một trường nội bộ không phải hợp đồng về ý nghĩa duy nhất của nó trong mọi trạng thái vòng đời.

### Capacity mặc định 16 có nghĩa gì?

API mô tả dung lượng ban đầu mặc định là `16`, hệ số tải `0.75`. Với hiện thực cấp phát trễ, điều đó tương ứng việc bảng đầu tiên thường có chiều dài `16` khi cần tạo, chứ không buộc một map vừa dựng phải đã có mảng 16 bucket trong bộ nhớ.

Hai phát biểu này không mâu thuẫn: một phát biểu về cấu hình ban đầu, một phát biểu về thời điểm hiện thực cấp phát.

### Không mở rộng vô hạn

Mã nguồn OpenJDK 17u dùng giới hạn `MAXIMUM_CAPACITY = 1 << 30` cho chiều dài bảng. Khi đã tới dung lượng tối đa, hiện thực không tiếp tục nhân đôi mảng vô hạn và có đường điều chỉnh ngưỡng tương ứng.

Giới hạn này nói về số bucket, không phải một lời hứa lưu được từng ấy đối tượng trong heap, cũng không phải cách đồng nhất capacity với số ánh xạ tối đa. Bộ nhớ có thể không đủ từ rất lâu trước khi chạm giới hạn đó. Không cần và không nên cấp một bảng cực lớn để kiểm chứng các công thức của bài.

Hàm lập kế hoạch ở phần sau chủ động từ chối yêu cầu vượt miền của nó. Kiểm tra số học chỉ bảo vệ phép tính và miền mô hình, không bảo đảm một lần cấp phát thực tế sẽ thành công.

## 6. Thí nghiệm đầy đủ: quan sát các mốc mở rộng

Chương trình dưới đây dùng reflection để quan sát hai trường private của hiện thực `HashMap`: `table` và `threshold`.

Đây là **thí nghiệm về hiện thực**, không phải cách viết mã ứng dụng phụ thuộc dung lượng. `HashMap` không công khai hai trường này. Lệnh chạy có `--add-opens java.base/java.util=ALL-UNNAMED` để cho chương trình thí nghiệm trong tiến trình đó truy cập phản chiếu vào gói tương ứng. Chỉ biên dịch mà bỏ tùy chọn khi chạy có thể bị cơ chế đóng gói module từ chối truy cập.

Mã nguồn OpenJDK 17u được dùng để giải thích cơ chế; kết quả dưới đây được đo trên JDK 24.0.2. Tên trường private và các số quan sát không phải giao diện được bảo đảm cho mọi hiện thực hoặc mọi phiên bản.

```java
import java.lang.reflect.Field;
import java.util.HashMap;

public class HashMapCapacityObservationDemo {
    private static final Field TABLE;
    private static final Field THRESHOLD;

    static {
        try {
            TABLE = HashMap.class.getDeclaredField("table");
            THRESHOLD = HashMap.class.getDeclaredField("threshold");
            TABLE.setAccessible(true);
            THRESHOLD.setAccessible(true);
        } catch (ReflectiveOperationException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    private static void show(String label, HashMap<?, ?> map)
            throws IllegalAccessException {
        Object[] table = (Object[]) TABLE.get(map);
        int length = table == null ? 0 : table.length;
        System.out.println(label + ": size=" + map.size()
                + ", tableLength=" + length
                + ", thresholdField=" + THRESHOLD.getInt(map));
    }

    record SameHashKey(int id) {
        @Override
        public int hashCode() {
            return 0;
        }
    }

    public static void main(String[] args) throws IllegalAccessException {
        HashMap<Integer, String> map = new HashMap<>(4, 0.75f);
        show("beforeAnyPut", map);
        map.put(1, "v1");
        show("afterPut1", map);
        map.put(2, "v2");
        map.put(3, "v3");
        show("afterPut3", map);
        map.put(1, "updated");
        show("afterOverwrite", map);
        map.put(4, "v4");
        show("afterPut4", map);
        map.put(5, "v5");
        map.put(6, "v6");
        show("afterPut6", map);
        map.put(7, "v7");
        show("afterPut7", map);
        map.remove(7);
        show("afterRemove", map);
        map.clear();
        show("afterClear", map);

        HashMap<Integer, Integer> defaults = new HashMap<>();
        show("defaultBeforePut", defaults);
        defaults.put(1, 1);
        show("defaultAfterPut", defaults);

        HashMap<Integer, Integer> rounded = new HashMap<>(17);
        show("requested17BeforePut", rounded);
        rounded.put(1, 1);
        show("requested17AfterPut", rounded);

        for (float factor : new float[] {0.5f, 0.75f, 1.0f}) {
            HashMap<Integer, Integer> sample = new HashMap<>(16, factor);
            sample.put(1, 1);
            show("factor" + factor, sample);
        }

        HashMap<Integer, Integer> fractional = new HashMap<>(16, 0.6f);
        for (int i = 0; i < 10; i++) {
            fractional.put(i, i);
        }
        show("factor0.6After10", fractional);

        HashMap<SameHashKey, Integer> collision = new HashMap<>(16);
        for (int i = 0; i < 9; i++) {
            collision.put(new SameHashKey(i), i);
        }
        show("collisionAfter9", collision);
    }
}
```

Lưu thành `HashMapCapacityObservationDemo.java`, biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 HashMapCapacityObservationDemo.java
java --add-opens java.base/java.util=ALL-UNNAMED HashMapCapacityObservationDemo
```

Đầu ra đã kiểm chứng:

```text
beforeAnyPut: size=0, tableLength=0, thresholdField=4
afterPut1: size=1, tableLength=4, thresholdField=3
afterPut3: size=3, tableLength=4, thresholdField=3
afterOverwrite: size=3, tableLength=4, thresholdField=3
afterPut4: size=4, tableLength=8, thresholdField=6
afterPut6: size=6, tableLength=8, thresholdField=6
afterPut7: size=7, tableLength=16, thresholdField=12
afterRemove: size=6, tableLength=16, thresholdField=12
afterClear: size=0, tableLength=16, thresholdField=12
defaultBeforePut: size=0, tableLength=0, thresholdField=0
defaultAfterPut: size=1, tableLength=16, thresholdField=12
requested17BeforePut: size=0, tableLength=0, thresholdField=32
requested17AfterPut: size=1, tableLength=32, thresholdField=24
factor0.5: size=1, tableLength=16, thresholdField=8
factor0.75: size=1, tableLength=16, thresholdField=12
factor1.0: size=1, tableLength=16, thresholdField=16
factor0.6After10: size=10, tableLength=32, thresholdField=18
collisionAfter9: size=9, tableLength=32, thresholdField=24
```

### 6.1. Chuỗi capacity 4 → 8 → 16

Trước lần `put` đầu, chưa có bảng, nên `tableLength=0`; `thresholdField=4` là thông tin chuẩn bị cho dung lượng mục tiêu.

Sau lần chèn đầu, bảng dài `4`, ngưỡng là `3`. Ba khóa vẫn nằm ở bảng dài `4`; ghi lại khóa `1` không làm tăng kích thước.

Khóa thứ `4` làm kích thước vượt ngưỡng `3`, bảng tăng lên `8`, ngưỡng `6`. Khóa thứ `6` chưa vượt `6`, còn khóa thứ `7` làm bảng tăng lên `16`, ngưỡng `12`.

### 6.2. Xóa và clear không thu nhỏ bảng trong quan sát này

Sau `remove`, kích thước giảm nhưng chiều dài bảng vẫn là `16`. Sau `clear`, map rỗng nhưng vẫn giữ bảng đã cấp phát.

Trong hiện thực OpenJDK được đối chiếu, `remove` và `clear` không tự thực hiện một cơ chế co bảng đối xứng với tăng bảng. `clear` bỏ các tham chiếu tới ánh xạ trong các bucket, không có nghĩa mọi phần bộ nhớ của cấu trúc lập tức được giải phóng.

Vì vậy không được dùng `size() == 0` để suy ra map chưa cấp phát hay đã trả hết bộ nhớ bảng băm.

### 6.3. Hệ số tải 0.6 và đường làm tròn

Ba hệ số `0.5`, `0.75`, `1.0` tạo các ngưỡng `8`, `12`, `16` cho bảng dài `16` trong mẫu.

Dòng `factor0.6After10` cho thấy bảng đã dài `32` và trường ngưỡng là `18`. Nó minh họa việc không áp công thức làm tròn lại tích một cách tuyệt đối ở mỗi lần tăng dung lượng.

### 6.4. Resize không chỉ có một nguyên nhân

Dòng `collisionAfter9` có kích thước `9`, bảng dài `32`, ngưỡng `24`. Các khóa có mã băm giống nhau nên tập trung vào một bucket.

Ở OpenJDK, khi bucket có quá nhiều nút, đường xử lý để chuyển sang cấu trúc cây còn xét dung lượng tối thiểu của bảng. Nếu bảng còn nhỏ, nó có thể chọn mở rộng trước. Trong mã nguồn đang xét, `MIN_TREEIFY_CAPACITY` là `64`; đây là một ngưỡng khác hoàn toàn với ngưỡng tải toàn map.

Vì vậy một bảng có thể tăng dung lượng dù `size` chưa vượt ngưỡng tải mà ta vừa tính. Không được gộp threshold của cả map với số nút trong một bucket thành cùng một khái niệm.

Bài không đi sâu thuật toán cây. Điều cần rút ra cho chủ đề này là **đủ dung lượng theo load factor không đồng nghĩa đã loại bỏ mọi khả năng mở rộng liên quan va chạm**.

## 7. Dự tính dung lượng khi biết số ánh xạ dự kiến

Giả sử dự kiến tối đa `N` khóa logic khác nhau cùng tồn tại và dùng load factor `f`. Mục tiêu thông thường là chọn một bảng có ngưỡng tải không nhỏ hơn `N`.

Một cách lập kế hoạch là:

```text
Dung lượng cần xét ≈ ceil(N / f)
        ↓
Chọn dung lượng bảng phù hợp với cách làm tròn của hiện thực
        ↓
Kiểm tra ngưỡng thực tế của cấu hình đó có đáp ứng N không
```

Với hệ số mặc định `0.75`, có thể dùng:

```text
ceil(N / 0.75) = ceil(4N / 3)
```

Đây là lập kế hoạch tránh mở rộng **do vượt ngưỡng tải** trong phạm vi cấu hình thông thường, không phải chứng minh mọi thao tác đều không thể mở rộng vì bất kỳ nguyên nhân nào. Va chạm, thao tác hàng loạt, giới hạn hiện thực và cách sử dụng dữ liệu vẫn phải được xem xét.

### 7.1. Vì sao new HashMap<>(100) chưa hẳn đủ cho 100 khóa mà không mở rộng?

Trong hiện thực đang xét:

```text
Đối số 100
    → dung lượng mục tiêu 128
    → ngưỡng mặc định 96

Đưa 100 khóa khác nhau bằng put:
    → lần thêm vượt 96 có thể làm mở rộng theo tải
```

Nếu lấy `ceil(100 / 0.75) = 134` làm đối số:

```text
Đối số 134
    → dung lượng mục tiêu 256
    → ngưỡng mặc định 192
```

Cách thứ hai cấp bảng lớn hơn từ lần cấp phát đầu, tránh bước từ `128` lên `256` do số khóa vượt `96`. Cả hai cuối cùng có thể đi tới bảng dài `256`, nhưng quá trình cấp phát và tổ chức lại dữ liệu khác nhau.

Không nên so sánh `100` và `134` rồi kết luận bộ nhớ cuối chỉ khác nhau `34` ô. Hiện thực làm tròn theo lũy thừa của hai, nên các bước dung lượng có tính rời rạc.

### 7.2. Đúng ngưỡng không bắt buộc cộng thêm một cách máy móc

Với `N=12`, lấy đối số `16` cho bảng có ngưỡng `12` ở hệ số mặc định. Trong chuỗi `put` thông thường đã mô tả, khóa thứ `12` chưa vượt ngưỡng; không phải cứ đạt đúng ngưỡng là phải mở rộng.

Một công thức bảo thủ có thể dự trù thêm, nhưng cần biết mình đang dự trù vì lý do gì. Cộng `1` tùy tiện có thể đẩy dung lượng mục tiêu qua một mốc lũy thừa của hai và tăng đáng kể bảng cấp phát.

Ngược lại, ép kiểu `(int)(N / 0.75)` làm tròn xuống không thể thay thế tùy ý cho phép lấy trần. Hãy kiểm tra phép toán, miền giá trị và cách constructor làm tròn thay vì chỉ sao chép một biểu thức.

### 7.3. N là số khóa đồng thời, không phải số lần ghi

Nếu xử lý một triệu bản cập nhật nhưng chỉ giữ `500` mã hàng khác nhau, không có cơ sở tự động chọn dung lượng theo một triệu lần cập nhật.

Nếu số khóa tăng lên một triệu rồi giảm xuống vài trăm, đó lại là một bài toán vòng đời khác: dung lượng đã tăng có thể được giữ lại. Cần xem mức đỉnh, thời gian sống của map và các lượt duyệt sau khi giảm dữ liệu.

Đoán dung lượng quá cao không miễn phí. Nó có thể làm lần cấp phát đầu tốn hơn và làm việc duyệt bảng kém hiệu quả dù `size` nhỏ.

## 8. Chương trình đầy đủ: lập kế hoạch với hệ số mặc định

Chương trình sau dùng phép tính số nguyên trên `long` để tính `ceil(4N/3)`, tránh việc nhân `int` bị tràn trước khi chia.

Các trường `modeledTable` và `modeledThreshold` là **giá trị mô hình tính theo quy tắc OpenJDK trong phạm vi ví dụ**, không phải trường nội bộ được chương trình đọc ra. `actualSize` mới là số ánh xạ được lấy từ map thật bằng API công khai.

Các trường hợp được chạy đều nhỏ và có `N>0`. Hàm kiểm tra miền lập kế hoạch không phải cam kết rằng hệ thống có đủ heap cho mọi giá trị được chấp nhận.

```java
import java.util.HashMap;

public class HashMapSizingDemo {
    private static int capacityArgumentForDefaultFactor(int expected) {
        if (expected < 0) {
            throw new IllegalArgumentException("negative expected count");
        }
        long requested = (4L * expected + 2) / 3;
        long maximumCapacity = 1L << 30;
        if (requested > maximumCapacity) {
            throw new IllegalArgumentException("outside planning range");
        }
        return (int) requested;
    }

    private static int modeledTableLength(int requested) {
        int capacity = 1;
        while (capacity < requested) {
            capacity <<= 1;
        }
        return capacity;
    }

    public static void main(String[] args) {
        for (int expected : new int[] {1, 3, 4, 12, 13, 100, 1000}) {
            int requested = capacityArgumentForDefaultFactor(expected);
            int tableLength = modeledTableLength(requested);
            int threshold = (int) (3L * tableLength / 4);

            HashMap<Integer, Integer> map = new HashMap<>(requested);
            for (int i = 0; i < expected; i++) {
                map.put(i, i);
            }
            System.out.println("expected=" + expected
                    + ", argument=" + requested
                    + ", modeledTable=" + tableLength
                    + ", modeledThreshold=" + threshold
                    + ", actualSize=" + map.size());
        }

        try {
            capacityArgumentForDefaultFactor(-1);
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            System.out.println("negativeExpected=IllegalArgumentException");
        }
    }
}
```

Lưu thành `HashMapSizingDemo.java`, biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 HashMapSizingDemo.java
java HashMapSizingDemo
```

Đầu ra đã kiểm chứng:

```text
expected=1, argument=2, modeledTable=2, modeledThreshold=1, actualSize=1
expected=3, argument=4, modeledTable=4, modeledThreshold=3, actualSize=3
expected=4, argument=6, modeledTable=8, modeledThreshold=6, actualSize=4
expected=12, argument=16, modeledTable=16, modeledThreshold=12, actualSize=12
expected=13, argument=18, modeledTable=32, modeledThreshold=24, actualSize=13
expected=100, argument=134, modeledTable=256, modeledThreshold=192, actualSize=100
expected=1000, argument=1334, modeledTable=2048, modeledThreshold=1536, actualSize=1000
negativeExpected=IllegalArgumentException
```

### Giải thích các mốc

- `N=3`: đối số `4`, bảng mô hình `4`, ngưỡng `3`.
- `N=4`: đối số tính được `6`, bảng mô hình làm tròn lên `8`, ngưỡng `6`.
- `N=12`: bảng mô hình `16`, ngưỡng `12`.
- `N=13`: đối số `18`, bảng mô hình `32`, ngưỡng `24`.
- `N=100`: đối số `134`, bảng mô hình `256`, ngưỡng `192`.
- `N=1000`: đối số `1334`, bảng mô hình `2048`, ngưỡng `1536`.

Việc map thật có đúng `N` ánh xạ xác nhận vòng chèn và dữ liệu đã tạo. Riêng dòng `actualSize` **không chứng minh map không mở rộng**; muốn quan sát dung lượng thực phải có một cơ chế quan sát phù hợp như thí nghiệm riêng ở phần 6.

Với `N=0`, một map rỗng có thể chưa cần cấp bảng. Không dùng hàm mô hình làm tròn của ví dụ để suy ra một bảng đang tồn tại khi chưa hề chèn dữ liệu.

### Vì sao không cấp một bảng khổng lồ “cho chắc”?

Vì chi phí liên quan không chỉ là số lần resize:

- Bảng lớn hơn giữ nhiều tham chiếu bucket hơn.
- Duyệt `HashMap` có chi phí liên quan cả capacity và size.
- Thời điểm cấp bảng có thể tạo áp lực cấp phát bộ nhớ.
- Ước lượng sai lớn có thể lãng phí suốt thời gian sống của map.
- Giá trị và đối tượng khóa vẫn cần bộ nhớ riêng.

Chọn trước dung lượng là một tối ưu có mục đích, không phải nguyên tắc “càng lớn càng tốt”. Với số lượng nhỏ hoặc khó biết trước, cấu hình mặc định thường đơn giản hơn; thay đổi khi có yêu cầu và bằng chứng cụ thể.

## 9. Resize và rehash thực sự làm gì?

Trong bối cảnh bảng băm, “rehash” thường được dùng để nói việc xây dựng lại cách phân bố các ánh xạ khi dung lượng thay đổi. Nhưng từ này dễ bị hiểu thành “gọi lại phương thức `hashCode` trên mọi khóa”.

Ở OpenJDK đang xét, mỗi nút lưu thông tin băm đã xử lý. Khi tăng dung lượng bảng, hiện thực có thể dùng thông tin đó để xác định vị trí mới mà không gọi lại `key.hashCode()` của từng khóa cũ.

Các bước khái niệm:

1. Xác định dung lượng mới và ngưỡng tương ứng.
2. Cấp mảng bucket mới.
3. Duyệt bảng cũ.
4. Đưa các nút hoặc các nhóm nút về bucket thích hợp trong bảng mới.
5. Để map tiếp tục truy cập ánh xạ thông qua bảng mới.

Các đối tượng khóa và giá trị không được sao chép sâu chỉ vì resize. Với các nhánh thông thường, hiện thực tái sử dụng cấu trúc nút; các nhánh cây có cách xử lý riêng. Không nên mô tả resize như việc tạo lại toàn bộ đối tượng nghiệp vụ.

### 9.1. Vì sao tăng gấp đôi thuận lợi với dung lượng lũy thừa hai?

Trong OpenJDK đang xét, với mã băm đã trộn `h` và chiều dài bảng `m` là lũy thừa hai, chỉ số được tính theo dạng:

```java
// Công thức hiện thực, không phải API Map chung.
int index = h & (m - 1);
```

Khi tăng từ `m` lên `2m`, mặt nạ có thêm đúng một bit cần xét. Một phần tử từ bucket cũ `j` có thể:

- Ở lại bucket `j` nếu bit bổ sung bằng `0`.
- Chuyển sang bucket `j + m` nếu bit bổ sung khác `0`.

Có thể biểu diễn phép phân nhóm bằng `h & m`.

Đây không phải cách chia ngẫu nhiên và không có nghĩa mọi phần tử trong một bucket đều đi cùng nhau. Các phần tử vốn trùng bucket ở bảng nhỏ có thể tách ra khi thêm bit phân biệt mới.

### 9.2. Ví dụ từ capacity 4 lên 8

Với các mã băm nhỏ `1`, `5`, `9`, `13`, phép trộn minh họa của OpenJDK không thay chúng vì phần bit cao đang bằng `0`.

```text
Bảng cũ 4: mặt nạ 3 = ...0011
Bảng mới 8: mặt nạ 7 = ...0111
Bit bổ sung:       4 = ...0100
```

| h | Chỉ số cũ: h & 3 | Bit xét thêm: h & 4 | Chỉ số mới: h & 7 |
|---:|---:|---:|---:|
| 1 | 1 | 0 | 1 |
| 5 | 1 | 4 | 5 |
| 9 | 1 | 0 | 1 |
| 13 | 1 | 4 | 5 |

Cả bốn phần tử đều ở bucket `1` trước đó. Sau tăng bảng, hai phần tử ở `1`, hai phần tử ở `5`.

Việc có thể tách như vậy không đảm bảo mọi va chạm sẽ biến mất. Nếu nhiều khóa có cùng toàn bộ mã băm đã xử lý, tăng số bit dùng để đánh chỉ số vẫn không phân biệt được chúng theo băm. Vì vậy tăng capacity không thay thế một cách phân bố mã băm phù hợp.

### 9.3. Raw hash, mã đã trộn và bucket index khác nhau

OpenJDK có bước trộn mã băm dạng `h ^ (h >>> 16)` cho khóa khác null. Thông tin lưu và dùng để phân bố không nên bị gọi lẫn với một chỉ số bucket cố định.

- `key.hashCode()` là mã băm do lớp khóa cung cấp.
- Phép xử lý của map tạo thông tin băm dùng trong hiện thực.
- Chiều dài bảng cùng thông tin đó quyết định bucket index.

Bucket index có thể đổi khi dung lượng đổi, dù định danh khóa và `key.hashCode()` không đổi. Cách đánh chỉ số bằng mặt nạ cũng không phải phép `hashCode % size`; dùng `size` thay capacity hoặc dùng phần dư âm thiếu xử lý là những mô hình sai.

## 10. Chương trình đầy đủ: mô hình chia bucket khi nhân đôi

Chương trình này **không đọc hoặc sửa một HashMap thật**. Nó tính các chỉ số theo công thức để minh họa bước phân nhóm khi tăng bảng từ `4` lên `8`.

```java
public class HashMapResizeSplitDemo {
    private static int spread(int rawHash) {
        return rawHash ^ (rawHash >>> 16);
    }

    public static void main(String[] args) {
        int oldCapacity = 4;
        int newCapacity = oldCapacity * 2;

        for (int rawHash : new int[] {1, 5, 9, 13}) {
            int storedHash = spread(rawHash);
            int oldIndex = storedHash & (oldCapacity - 1);
            int newIndex = storedHash & (newCapacity - 1);
            int extraBit = storedHash & oldCapacity;
            System.out.println("raw=" + rawHash
                    + ", oldIndex=" + oldIndex
                    + ", extraBit=" + extraBit
                    + ", newIndex=" + newIndex);
        }
    }
}
```

Lưu thành `HashMapResizeSplitDemo.java`, biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 HashMapResizeSplitDemo.java
java HashMapResizeSplitDemo
```

Đầu ra đã kiểm chứng:

```text
raw=1, oldIndex=1, extraBit=0, newIndex=1
raw=5, oldIndex=1, extraBit=4, newIndex=5
raw=9, oldIndex=1, extraBit=0, newIndex=1
raw=13, oldIndex=1, extraBit=4, newIndex=5
```

Hai dòng có `extraBit=0` giữ chỉ số `1`; hai dòng có `extraBit=4` chuyển sang `5 = 1 + 4`.

Mô hình giúp giải thích thuật toán, không phải một API cho ứng dụng tự quản lý bucket. Khi dùng `HashMap` bình thường, ứng dụng chỉ thao tác qua khóa và giá trị; không cần tính trước bucket để tra cứu.

Thứ tự duyệt có thể thay đổi khi cấu trúc bảng thay đổi. `HashMap` vốn không bảo đảm thứ tự; việc một nhóm nút giữ thứ tự tương đối trong một nhánh xử lý nội bộ không tạo cam kết về thứ tự toàn map.

## 11. Chương trình đầy đủ: resize có gọi lại hashCode của khóa cũ không?

Ví dụ dưới đây dùng khóa có bộ đếm lời gọi `hashCode`. Mã băm trả về vẫn là `id` bất biến; bộ đếm chỉ để quan sát, không tham gia quan hệ bằng nhau hoặc giá trị mã băm.

Đây là thí nghiệm về số lần gọi trên hiện thực đang chạy, không phải số lượng lời gọi được API `HashMap` bảo đảm vĩnh viễn. Không viết nghiệp vụ phụ thuộc vào việc một phương thức băm được gọi đúng một số lần nhất định.

```java
import java.util.HashMap;

public class HashMapStoredHashDemo {
    static final class TrackedKey {
        private final int id;
        private int hashCalls;

        TrackedKey(int id) {
            this.id = id;
        }

        @Override
        public int hashCode() {
            hashCalls++;
            return id;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof TrackedKey key && id == key.id;
        }
    }

    public static void main(String[] args) {
        TrackedKey[] keys = {
            new TrackedKey(1),
            new TrackedKey(5),
            new TrackedKey(9),
            new TrackedKey(13)
        };
        HashMap<TrackedKey, String> map = new HashMap<>(4, 0.75f);

        for (int i = 0; i < 3; i++) {
            map.put(keys[i], "v" + keys[i].id);
        }
        System.out.println("sizeBeforeFourth=" + map.size());

        map.put(keys[3], "v13");
        System.out.println("sizeAfterFourth=" + map.size());
        for (TrackedKey key : keys) {
            System.out.println("id=" + key.id
                    + ", observedHashCalls=" + key.hashCalls);
        }

        boolean allPresent = true;
        for (TrackedKey key : keys) {
            String value = map.get(new TrackedKey(key.id));
            allPresent &= ("v" + key.id).equals(value);
        }
        System.out.println("allMappingsPresent=" + allPresent);
    }
}
```

Lưu thành `HashMapStoredHashDemo.java`, biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 HashMapStoredHashDemo.java
java HashMapStoredHashDemo
```

Đầu ra đã kiểm chứng:

```text
sizeBeforeFourth=3
sizeAfterFourth=4
id=1, observedHashCalls=1
id=5, observedHashCalls=1
id=9, observedHashCalls=1
id=13, observedHashCalls=1
allMappingsPresent=true
```

### Điều được quan sát

Map được tạo với dung lượng mục tiêu `4` và load factor `0.75f`. Chuỗi thêm bốn khóa khác nhau đi qua mốc mở rộng do tải đã giải thích ở các phần trước.

Sau lần thêm thứ tư, mỗi đối tượng khóa vẫn chỉ ghi nhận một lời gọi `hashCode` từ lần đưa vào của nó. Các khóa cũ không bị gọi lại hàm băm chỉ để phân bố lại trong lần resize này.

Những lần `get` sau đó dùng các đối tượng thăm dò mới. Bộ đếm của các đối tượng mới không được trộn vào các dòng bộ đếm đã in của đối tượng khóa ban đầu. `allMappingsPresent=true` xác nhận các ánh xạ vẫn tra được sau chuỗi chèn.

Từ kết quả này có thể hiểu đúng cách dùng từ “rehash” trong hiện thực đang xét: tổ chức lại bucket dựa trên thông tin băm đã lưu, không bắt buộc tính lại hàm băm nghiệp vụ của mọi khóa cũ.

### Resize không sửa một khóa có hợp đồng sai

Nếu đối tượng khóa bị thay đổi thông tin tham gia `equals` hoặc `hashCode` sau khi đưa vào map, không được mong resize sẽ tự tính lại và sửa trạng thái cho ứng dụng.

Thực tế việc sử dụng thông tin băm đã lưu là một lý do càng không nên dựa vào kỳ vọng đó. Điều cần làm là giữ định danh khóa ổn định trong thời gian làm khóa, không tìm một thời điểm resize để sửa hộ lỗi thiết kế.

Bộ đếm trong ví dụ là dụng cụ thí nghiệm một luồng. Một cách triển khai `hashCode` dùng trong ứng dụng thường nên đơn giản, ổn định và không mang tác động nghiệp vụ theo số lần gọi.

## 12. Chi phí mở rộng và ý nghĩa của O(1) khấu hao

Một lần `put` không phải lúc nào cũng chỉ sửa một nút. Nếu nó kích hoạt mở rộng, map có thể phải cấp bảng mới và đi qua các bucket cùng các ánh xạ cũ.

Chi phí một lần resize liên quan dung lượng bảng cũ và số ánh xạ phải tổ chức lại. Nó có thể đáng kể so với một lần chèn thông thường.

Vì dung lượng thường tăng theo cấp số nhân, các lần mở rộng không xảy ra sau mọi lần thêm. Với một chuỗi chèn và điều kiện phân bố băm hợp lý, tổng chi phí mở rộng được phân bổ qua nhiều lần thao tác. Đó là ý nghĩa của **khấu hao (amortized)** khi nói về chi phí chèn bình thường.

Ví dụ về tổng các chiều dài bảng theo một chuỗi nhân đôi:

```text
16 + 32 + 64 + ... + M
```

Tổng này cùng bậc với `M`, không phải mỗi lần chèn đều phải di chuyển toàn bộ dữ liệu từ đầu. Nhưng một thao tác cụ thể tại mốc mở rộng vẫn có thể chậm hơn hẳn thao tác ngay trước nó.

Cần phân biệt:

- Giả định phân bố băm tốt nói về khả năng các khóa phân bố vào bucket.
- Khấu hao nói về cách chia chi phí các đợt mở rộng trên cả chuỗi thao tác.
- Cả hai không biến từng lần `put` thành một bảo đảm thời gian cố định bất kể dữ liệu và công việc của `hashCode`/`equals`.

Nếu ứng dụng nhạy với một đợt trễ riêng lẻ, giảm số resize bằng ước lượng dung lượng có thể hữu ích. Muốn kết luận về độ trễ thật vẫn cần đo dưới tải phù hợp, gồm cấp phát và thu gom rác.

### Bộ nhớ đỉnh cũng cần xét

Trong lúc mở rộng, bảng mới được cấp phát trong khi việc chuyển dữ liệu từ bảng cũ chưa hoàn tất. Vì vậy tạm thời có thể tồn tại cả hai mảng bucket, làm nhu cầu bộ nhớ đỉnh cao hơn trạng thái ổn định sau đó.

Không nên suy rằng mọi khóa và giá trị đều được nhân đôi sâu; đó không phải cơ chế đã mô tả. Nhưng cũng không nên chỉ nhìn dung lượng cuối rồi bỏ qua chi phí chuyển tiếp.

Số byte thực tế phụ thuộc cấu trúc hiện thực, kích thước tham chiếu, đối tượng khóa/giá trị, cấu hình JVM và dữ liệu. Capacity là số bucket, không phải một đơn vị byte.

## 13. Chọn load factor và vòng đời map theo yêu cầu

### Khi nên cân nhắc initial capacity

Có ích khi biết khá rõ số ánh xạ sẽ được nạp, map có kích thước đáng kể, hoặc muốn giảm các đợt mở rộng trong một giai đoạn xử lý nhạy về độ trễ.

Ước lượng nên tính theo số khóa cùng tồn tại và có biên dự phòng có lý do. Không cấp theo toàn bộ số sự kiện tích lũy nếu chúng liên tục cập nhật cùng một tập khóa nhỏ.

### Khi chưa nên tùy biến load factor

Nếu chưa có vấn đề đo được, thay hệ số mặc định có thể chỉ đổi một chi phí chưa hiểu sang một chi phí khác.

- Giảm hệ số có thể tăng số bucket và chi phí duyệt bảng.
- Tăng hệ số có thể giảm bộ nhớ bảng nhưng tăng công việc trong bucket.
- Mã băm kém hoặc nhiều khóa cùng một hash không được chữa đơn giản bằng việc thay hệ số.
- Khóa có hợp đồng sai vẫn sai bất kể hệ số nào.

Nếu chọn một hệ số khác, hãy kiểm tra cả giai đoạn xây map, tra cứu, cập nhật, duyệt và mức bộ nhớ phù hợp với ứng dụng, thay vì chỉ một phép đo nhỏ.

### Khi map từng rất lớn rồi thu nhỏ dữ liệu

Ở OpenJDK đang xét, xóa các ánh xạ không tự co bảng. Nếu map sống lâu, giảm từ rất nhiều khóa xuống rất ít khóa và tiếp tục được duyệt thường xuyên, bảng lớn có thể vẫn là một chi phí.

Một lựa chọn có thể cân nhắc sau khi đo là dựng một map mới theo quy mô dữ liệu hiện tại và chuyển các ánh xạ còn cần giữ. Đây không phải một lời gọi “trim” công khai trên `HashMap`.

Đoạn minh họa khi đang sở hữu độc quyền nguồn:

```java
HashMap<K, V> rebuilt = new HashMap<>(source);
```

Đoạn trên dùng các tham số kiểu `K`, `V` và biến `source` có sẵn trong ngữ cảnh ứng dụng; không phải chương trình độc lập. Nó chép các ánh xạ sang map khác, không sao chép sâu khóa/giá trị và không tự cập nhật các tham chiếu hoặc view vẫn trỏ tới map cũ.

Constructor chép có chính sách của nó; không mặc định mọi tham số tùy biến của map nguồn đều được giữ nguyên. Việc chuyển sang map mới cũng có chi phí cấp phát và chép, nên không nên thực hiện máy móc sau mỗi lần xóa.

### Resize không phải cơ chế đồng bộ

`HashMap` không tự cung cấp đồng bộ cho nhiều luồng thay đổi cấu trúc. Chọn capacity lớn để “chắc không resize” không làm nó trở thành một cấu trúc an toàn cho mọi truy cập đồng thời.

Một lần chèn mới đã là thay đổi cấu trúc, bất kể có resize hay không. Khi nhiều luồng chia sẻ dữ liệu, cần thiết kế phối hợp hoặc chọn cấu trúc có hợp đồng phù hợp. Các ví dụ của bài dùng một luồng để tập trung vào chính sách dung lượng.

## 14. Những cách hiểu sai cần tránh

| Cách hiểu sai | Cách đọc đúng |
|---|---|
| Capacity là size | Capacity đếm bucket; size đếm ánh xạ |
| Constructor `HashMap<>(N)` thêm sẵn N phần tử | Map vẫn rỗng; N liên quan dung lượng ban đầu |
| Load factor 0.75 nghĩa 75% bucket chắc chắn có dữ liệu | Đây là hệ số tải theo số ánh xạ và dung lượng, không phải phép đếm bucket không rỗng |
| Đạt đúng threshold là luôn resize | Chuỗi `put` thông thường xét việc vượt ngưỡng; các đường hiện thực khác cần xem riêng |
| Chỉ vượt load threshold mới được resize | Xử lý va chạm có thể kích hoạt mở rộng khi bảng còn nhỏ |
| Rehash luôn gọi lại hashCode của mọi khóa cũ | OpenJDK có thể phân bố lại bằng thông tin băm đã lưu |
| HashMap tự giảm capacity sau remove/clear | Hiện thực quan sát giữ bảng; không có cơ chế co tự động đối xứng ở các thao tác đó |
| Capacity càng lớn thì càng nhanh | Bộ nhớ và chi phí duyệt có thể tăng |
| Tránh resize là đủ để HashMap an toàn đa luồng | Đồng bộ là yêu cầu riêng, không được giải quyết bằng dung lượng |
| Đổi load factor sẽ chữa equals/hashCode sai | Hợp đồng khóa phải được sửa ở lớp khóa và cách sử dụng |

## 15. Tự kiểm tra trước khi chạy ví dụ

### Câu 1: Capacity 16, hệ số 0.75

Trong chuỗi `put` khóa mới thông thường, giả sử không có mở rộng sớm do va chạm, threshold là `12`. Sau khóa thứ `12` có bắt buộc mở rộng do tải chưa? Sau khóa thứ `13` thì sao?

**Đáp án:** Khóa thứ `12` mới đạt ngưỡng, chưa vượt. Khóa thứ `13` vượt ngưỡng và đi qua đường mở rộng do tải đã mô tả.

### Câu 2: Ghi một khóa nhiều lần

Map có `size=12`, threshold `12`. Gọi `put` một nghìn lần chỉ để thay giá trị của một khóa đã có. Có thể suy số ánh xạ tăng thêm một nghìn không?

**Đáp án:** Không. Ghi lại khóa logic đang có thay giá trị, không tạo thêm một nghìn ánh xạ và không đi theo đường tăng size do thêm khóa mới.

### Câu 3: Load factor không phải occupancy

Map có `12` ánh xạ và bảng dài `16`. Có chắc có đúng `12` bucket không rỗng không?

**Đáp án:** Không. Nhiều ánh xạ có thể nằm cùng bucket. Mức tải trung bình `12/16` không đồng nghĩa số bucket không rỗng.

### Câu 4: Đối số 100

Theo quy tắc OpenJDK đang xét, đối số initial capacity `100` thường hướng tới bảng dài bao nhiêu và ngưỡng mặc định bao nhiêu?

**Đáp án:** Bảng mục tiêu `128`, threshold thông thường `96` sau khi cấp phát. Vì vậy chưa thể dùng đối số `100` như lời hứa chứa `100` khóa khác nhau mà không mở rộng theo tải.

### Câu 5: Kế hoạch cho 100 khóa

Với load factor `0.75`, `ceil(100/0.75)` bằng bao nhiêu? Dung lượng mô hình sau làm tròn là bao nhiêu?

**Đáp án:** Đối số dự tính `134`, bảng mô hình `256`, ngưỡng mặc định `192`. Điều này lập kế hoạch theo tải, không loại trừ mọi nguyên nhân mở rộng khác.

### Câu 6: Mảng chưa tồn tại

Reflection thấy `tableLength=0`, `thresholdField=32` ngay sau `new HashMap<>(17)`. Có được diễn giải là một bảng dài `32` đã cấp phát không?

**Đáp án:** Không. Đó là thông tin dung lượng mục tiêu trước cấp phát trong hiện thực này. Phải phân biệt trạng thái trường nội bộ trước và sau khi bảng tồn tại.

### Câu 7: Bucket cũ 1, capacity 4

Một mã băm đã xử lý có `h & 3 = 1` và `h & 4 = 4`. Khi bảng tăng từ `4` lên `8`, chỉ số mới là gì?

**Đáp án:** `1 + 4 = 5`. Bit bổ sung quyết định chuyển sang nhóm cao.

### Câu 8: Tất cả hash giống nhau

Nếu các khóa khác nhau có cùng toàn bộ mã băm đã xử lý, nhân đôi bảng có chắc phân tán chúng sang các bucket khác nhau không?

**Đáp án:** Không. Cùng thông tin băm dẫn tới cùng các bit dùng để chọn chỉ số. Cần phân biệt giữa thêm dung lượng và chất lượng phân bố mã băm.

### Câu 9: Rehash có sửa khóa bị đổi không?

Một khóa bị sửa thông tin xác định mã băm khi đang trong map. Có nên chèn thêm dữ liệu để mong resize gọi lại hashCode và chữa vấn đề không?

**Đáp án:** Không. Hiện thực có thể dùng mã băm đã lưu, và điều kiện ổn định của khóa đã bị vi phạm. Phải sửa thiết kế và cách sử dụng khóa.

### Câu 10: clear rồi size 0

Sau khi map từng lớn, `clear()` đưa size về `0`. Có bảo đảm mảng bucket cũng về trạng thái chưa cấp phát không?

**Đáp án:** Không. Thí nghiệm và mã nguồn OpenJDK cho thấy bảng có thể được giữ lại. Kích thước logic bằng 0 không đủ mô tả bộ nhớ cấu trúc.

### Câu 11: Hệ số 0.6

Một bảng `16` có threshold `9`, sau đó đường mở rộng nhân đôi threshold cũ khi bảng lên `32`. Ngưỡng có bắt buộc là `floor(32 × 0.6)=19` không?

**Đáp án:** Không. Đường nhân đôi đang xét tạo `18`. Công thức tích là mô hình chính sách; số nội bộ chính xác phụ thuộc các bước hiện thực.

### Câu 12: Một put chậm tại mốc mở rộng

Điều đó có mâu thuẫn với việc nói chi phí chèn thường được phân tích O(1) khấu hao trong điều kiện thích hợp không?

**Đáp án:** Không. Khấu hao phân bổ chi phí các đợt mở rộng qua chuỗi thao tác; không hứa mọi lần chèn riêng lẻ có cùng thời gian.

## 16. Thực hành: lập bảng dự báo rồi đối chiếu

### Phần A — Cấu hình mặc định

Không dùng reflection trước khi dự đoán. Xét một chuỗi thêm khóa khác nhau bằng `put`, không có xử lý va chạm kích hoạt mở rộng sớm:

1. Bảng hiện tại dài `8`, load factor `0.75`.
2. Viết threshold tương ứng.
3. Dự đoán chiều dài bảng sau khi size lần lượt là `5`, `6`, `7`.
4. Sau size `7`, thay giá trị một khóa đã có rồi xóa một khóa.
5. Nêu điều gì thay đổi ở size, điều gì không tự thay đổi về capacity trong hiện thực đang xét.

**Kết quả cần đạt:** ngưỡng ban đầu `6`; size `5` và `6` vẫn ở bảng `8`; lần thêm để lên `7` đi tới bảng `16`. Ghi lại khóa không tăng size; xóa làm size giảm, không tự co bảng theo mô tả OpenJDK của bài.

Sau đó có thể sửa chương trình quan sát để đối chiếu trên runtime đang dùng, vẫn ghi rõ đây là quan sát trường private.

### Phần B — Dung lượng cho một đợt nạp

Dự kiến `500` khóa khác nhau, hệ số mặc định:

1. Tính `ceil(500/0.75)`.
2. Làm tròn dung lượng mục tiêu theo lũy thừa của hai.
3. Tính ngưỡng mặc định của bảng đó.
4. So với việc truyền thẳng `500` làm initial capacity.

**Đáp án:** đối số dự tính `667`, bảng mục tiêu `1024`, ngưỡng `768`. Truyền thẳng `500` hướng tới bảng `512`, ngưỡng `384`, nên đợt nạp `500` khóa có thể phải mở rộng theo tải.

### Phần C — Đo mà không nhầm điều đã đo

Nếu dùng chương trình cộng thời gian để so hai cấu hình, hãy ghi rõ:

- Thời gian đang gồm tạo map, cấp phát bảng, thêm khóa hay chỉ tra cứu?
- Dữ liệu có cùng số khóa logic và cùng đặc tính băm không?
- Có phải đang so một lần chạy ngắn chịu ảnh hưởng khởi động/JIT/GC không?
- Có quan sát bộ nhớ và các lượt duyệt sau khi nạp không?
- Kết luận là về dữ liệu và môi trường nào, hay đang suy quá rộng?

Mục tiêu của bài thực hành là hiểu và kiểm chứng chính sách dung lượng, không biến một phép đo ngẫu nhiên thành lời khẳng định mọi chương trình phải dùng cùng một cấu hình.

## Tài liệu đối chiếu

- [Java 17 — HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): capacity, load factor, chính sách rehash, constructor và chi phí duyệt.
- [Mã nguồn OpenJDK 17u — HashMap.java](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/HashMap.java): cấp phát trễ, `tableSizeFor`, `putVal`, `resize`, chia bucket và xử lý dung lượng tối thiểu khi chuyển bucket sang cây.

Các chương trình có lệnh biên dịch/chạy đầy đủ. Mã được kiểm chứng bằng `javac --release 17 -encoding UTF-8` và chạy trên JDK 24.0.2. Những công thức mô hình, phép đo lời gọi và truy cập private được đánh dấu theo đúng phạm vi; không xem chúng là API công khai của mọi `Map` hay mọi Java runtime.
