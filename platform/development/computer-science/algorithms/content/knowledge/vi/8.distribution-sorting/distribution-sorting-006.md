# Lựa chọn cơ số và số lượt phân phối

Trong **sắp xếp phân phối**, thay vì so sánh trực tiếp từng cặp phần tử, ta dùng thông tin về **khóa** để đưa phần tử vào các nhóm (bucket), sau đó ghép lại theo quy tắc. Với **radix sort (sắp xếp theo cơ số)**, khóa số nguyên được xem như một dãy chữ số trong cơ số `B`; mỗi lượt phân phối xử lý một vị trí chữ số. Chọn `B` quyết định **số nhóm mỗi lượt**, **số lượt cần thực hiện**, lượng bộ nhớ tạm và chi phí thiết lập nhóm. Vì thế chọn cơ số không đơn thuần là chọn “số càng lớn càng tốt”.

Bài này tập trung vào **LSD radix sort** (Least Significant Digit: xử lý chữ số thấp nhất trước), nơi mỗi lượt phân phối phải **ổn định (stable)**. Ta sẽ học cách tính số lượt chính xác, chọn cơ số theo giới hạn dữ liệu, chứng minh tính đúng và xây dựng ví dụ Java 17+ hỗ trợ cả số nguyên âm, số trùng nhau và các giá trị biên của `int`.

## 1. “Cơ số” và “lượt phân phối” nghĩa là gì?

Số nguyên không âm `x` khi viết theo cơ số `B≥2` có các chữ số `d_0,d_1,...` sao cho:

```text
x = d_0 + d_1*B + d_2*B^2 + ...
0 <= d_i < B
```

- **Cơ số `B`:** mỗi chữ số nhận một trong `B` giá trị, từ `0` đến `B−1`. Vì thế một lượt có thể cần đến **`B` bucket**, hoặc một mảng đếm kích thước `B`.
- **Lượt phân phối (digit pass):** duyệt phần tử và đưa nó vào bucket ứng với **một chữ số tại vị trí được chọn**, rồi ghép các bucket theo thứ tự chữ số.
- **LSD radix sort:** phân phối chữ số đơn vị trước, rồi chữ số tiếp theo, từ thấp đến cao. Sau lượt cuối cùng, toàn bộ khóa ở đúng thứ tự.

Ví dụ số `275` theo cơ số `10` có các chữ số từ thấp đến cao là `5,7,2`; theo cơ số `2`, nó có biểu diễn nhị phân và nhiều vị trí bit hơn. Cùng một số nhưng độ dài biểu diễn và số lượt phân phối có thể khác nhau.

**Phân biệt hai việc:** Một lượt phân phối **không phải** là một phép so sánh. Nếu dùng counting sort ổn định cho mỗi chữ số, ta đếm bucket, tính vị trí bắt đầu và chuyển phần tử đến mảng đích, không so sánh hai khóa đầy đủ để quyết định thứ tự.

## 2. Ví dụ trực quan: cơ số 10 với ba lượt

Xét các số **không âm**:

```text
[170, 45, 75, 90, 802, 24, 2, 66]
```

Giá trị lớn nhất `802` cần **3 chữ số thập phân**, nên LSD radix sort cơ số `10` có ba lượt: hàng đơn vị, hàng chục, hàng trăm. Số thiếu chữ số cao được xem như có chữ số `0` ở phía trước (`2` được coi là `002`).

| Lượt | Chữ số làm khóa phân phối | Thứ tự sau khi ghép bucket ổn định |
| --- | --- | --- |
| Ban đầu | Chưa phân phối | `[170,45,75,90,802,24,2,66]` |
| 1 | Hàng đơn vị: `x % 10` | `[170,90,802,2,24,45,75,66]` |
| 2 | Hàng chục: `(x/10) % 10` | `[802,2,24,45,66,170,75,90]` |
| 3 | Hàng trăm: `(x/100) % 10` | `[2,24,45,66,75,90,170,802]` |

Lượt 1 nhóm các giá trị theo chữ số cuối `0,2,4,5,6`. Hai số `802` và `2` đều có hàng đơn vị bằng `2`, nên **giữ thứ tự tương đối ban đầu** trong bucket `2`. Lượt 2 xử lý hàng chục nhưng cần bảo toàn thứ tự theo hàng đơn vị trong những nhóm có cùng hàng chục. Lượt 3 tương tự với hàng trăm.

Nếu chọn cơ số `1000`, mọi số trong ví dụ chỉ cần **một chữ số cơ số 1000**, nghĩa là **một lượt**, nhưng sẽ có đến **1000 bucket khả dĩ** thay cho 10. Với chỉ tám phần tử, chi phí khởi tạo/duyệt 1000 bucket thường không đáng để tiết kiệm hai lượt.

## 3. Công thức số lượt phân phối

### Khóa không âm với giá trị tối đa U

Với cơ số `B≥2` và **ít nhất một giá trị dương** trong dãy, số chữ số cần để biểu diễn số lớn nhất `U>0` là:

```text
d = floor(log_B(U)) + 1
  = ceil(log_B(U + 1))
```

Đây là số lượt LSD cần nếu mỗi lượt xử lý **đúng một chữ số cơ số B**, bao gồm các chữ số cao bằng 0 ở những số ngắn hơn.

Ví dụ:

| Giá trị lớn nhất `U` | Cơ số `B` | Số lượt `d` |
| ---: | ---: | ---: |
| `802` | `10` | `3` |
| `802` | `100` | `2` |
| `802` | `1000` | `1` |
| `255` | `2` | `8` |
| `255` | `16` | `2` |
| `255` | `256` | `1` |
| `1000` | `10` | `4` |

Với `U=0` và dãy không rỗng, có thể **bỏ hẳn công việc sắp** vì mọi phần tử đều bằng 0; nếu dùng khuôn LSD cần ít nhất một lượt để xử lý “một chữ số”, quy ước `d=1` cũng hợp lệ. Với mảng rỗng, có thể trả ngay, **`0` lượt**. Không nên máy móc áp công thức logarit với `U=0` hoặc mảng rỗng rồi truy cập dữ liệu không tồn tại.

**Tránh dùng logarit số thực khi cần ranh giới chính xác.** Sai số làm tròn gần lũy thừa của `B` có thể khiến số lượt thiếu hoặc thừa một. Một cách số nguyên an toàn cho số không âm là đếm bằng chia lặp `U/=B` cho tới khi `U=0` (với `U=0` xử lý riêng). Không tính trực tiếp `B^k` trong `int` nếu có nguy cơ tràn số.

### Khóa có độ rộng cố định w bit

Với khóa có thể nhận **tất cả** `2^w` tổ hợp bit và cơ số là lũy thừa của 2:

```text
B = 2^r             (r bit mỗi chữ số)
d = ceil(w / r)      (số lượt)
```

Ví dụ `int` của Java có độ rộng **32 bit**, nên:

| Bit mỗi chữ số `r` | Cơ số `B=2^r` | Lượt `d=ceil(32/r)` | Dung lượng mảng đếm `B` phần tử `int` |
| ---: | ---: | ---: | ---: |
| `1` | `2` | `32` | 2 |
| `4` | `16` | `8` | 16 |
| `8` | `256` | `4` | 256 |
| `11` | `2048` | `3` | 2048 |
| `16` | `65.536` | `2` | 65.536 |

Nếu `32` không chia hết cho `r`, lượt cuối chỉ có **một phần số bit** thật. Ví dụ `r=11` có các lượt bắt đầu ở bit `0,11,22`; lượt cao nhất chỉ chứa **10 bit**, phần bit “đệm” ở trên được xem là 0. Áp mask `B−1` sau khi dịch phải không dấu xử lý tự nhiên trường hợp này.

**Lưu ý:** Số lượt cố định theo `w` có thể cao hơn số lượt tối thiểu của **một tập dữ liệu cụ thể**. Đổi lại, cách cố định dễ bảo đảm đúng cho cả số âm và giá trị biên. Nếu quyết định tự bỏ các lượt cao, phải chứng minh phần khóa còn lại không làm thay đổi thứ tự và không được đánh mất thông tin dấu.

## 4. Chọn cơ số: ít lượt chưa chắc nhanh

Xét LSD radix sort sử dụng **counting sort ổn định** cho từng chữ số:

1. Đếm bao nhiêu phần tử rơi vào mỗi bucket, `O(n)`.
2. Tính vị trí bắt đầu của từng bucket bằng tổng tiền tố, `O(B)`.
3. Duyệt đầu vào và ghi vào mảng đích đúng vị trí, `O(n)`.
4. Đổi vai trò hai mảng và chuyển sang chữ số cao hơn.

Do đó:

```text
Chi phí một lượt:  Θ(n + B)
Tổng d lượt:       Θ(d * (n + B))
Bộ nhớ phụ:        Θ(n + B)
```

Với khóa `w` bit và `B=2^r`:

```text
T(r) = Θ(ceil(w/r) * (n + 2^r))
M(r) = Θ(n + 2^r)
```

Đây là mô hình tiệm cận cho **cài đặt dùng mảng đếm kích thước B và mảng phân phối n phần tử**. Hằng số thực tế còn tùy cache CPU, tốc độ truy cập bộ nhớ, chi phí cấp phát, hiệu quả vòng lặp và kiểu phần tử.

- **Cơ số nhỏ:** ít bucket, mảng đếm gọn, nhưng cần nhiều lượt, phải đọc/ghi toàn bộ input nhiều lần.
- **Cơ số lớn:** ít lượt, nhưng mảng đếm lớn, chi phí xóa/duyệt bucket lớn, có thể vượt cache hoặc giới hạn RAM.
- **Khi `B≫n`:** phần lớn bucket trống, vẫn tốn `O(B)` thao tác trong counting sort kiểu mảng đếm; một cơ số quá lớn có thể làm thuật toán **chậm hơn**.
- **Khi `n` rất lớn:** chi phí đi qua toàn bộ phần tử nhiều lượt có thể chiếm ưu thế, nên tăng `r` đôi khi có lợi nếu mảng đếm vẫn phù hợp bộ nhớ/cache.
- **Khi khóa ngắn hoặc phạm vi giá trị hẹp:** có thể giảm số lượt hoặc dùng **counting sort trực tiếp** nếu miền giá trị đủ nhỏ. Không nên chọn radix sort chỉ vì thấy dữ liệu là số nguyên.

Với `r=8`, `B=256`, mảng `int[256]` xấp xỉ 1 KiB dữ liệu phần tử; `r=16` cần `int[65536]` xấp xỉ 256 KiB, chưa kể đối tượng mảng và hai mảng nguồn/đích. `r=11` là một điểm trung gian 2048 bucket, ba lượt. Các con số này giúp hình dung đánh đổi; **không có cơ số tối ưu chung cho mọi JVM, CPU và bộ dữ liệu**.

Một tiêu chí chọn cơ số hợp lý là đo thời gian/memory **trên dữ liệu đại diện** bằng cùng hợp đồng và đầu ra, thay vì suy luận “`d` nhỏ nhất thì nhanh nhất”. Với `B=2^32` để sắp toàn bộ `int` trong một lượt, mảng đếm cần hàng tỷ bucket: không thực tế trong cài đặt Java thông thường dù `d=1`.

## 5. Vì sao LSD bắt buộc phân phối ổn định?

**Ổn định** nghĩa là trong cùng bucket của **chữ số đang xử lý**, các phần tử giữ nguyên thứ tự tương đối mà chúng có trước lượt phân phối.

Bất biến sau `k` lượt LSD:

> Mảng đã được sắp xếp theo **k chữ số thấp nhất** của khóa; nếu hai phần tử có cùng k chữ số thấp thì thứ tự tương đối trước xử lý vẫn được giữ.

**Cơ sở `k=1`:** Phân phối ổn định theo chữ số thấp nhất tạo các nhóm theo thứ tự `0..B−1`, nên mảng đã sắp theo chữ số đó.

**Bước quy nạp:** Giả sử đã đúng cho `k` chữ số thấp. Lượt `k+1` phân phối theo chữ số mới cao hơn: mọi khóa có chữ số mới nhỏ hơn được đặt trước; **trong nhóm cùng chữ số mới**, phân phối ổn định giữ nguyên thứ tự đã sắp theo k chữ số thấp. Vì vậy sau lượt này, mảng sắp đúng theo `k+1` chữ số thấp.

**Kết thúc:** Khi xử lý hết `d` chữ số đủ biểu diễn khóa, thứ tự theo d chữ số chính là thứ tự toàn khóa. Đây là cơ sở chứng minh LSD radix sort **đúng**, với giả định phép lấy chữ số và thứ tự bucket phản ánh quan hệ so sánh yêu cầu.

Nếu một lượt đảo lung tung các phần tử cùng bucket, các chữ số thấp đã sắp ở lượt trước có thể mất thứ tự; lượt chữ số cao không sửa lại sai lệch đó. Do vậy không được dùng một thuật toán phân phối **không ổn định** rồi mặc nhiên kết luận LSD radix sort đúng.

### Cách phân phối ổn định bằng mảng vị trí bắt đầu

Sau bước đếm, đặt `next[b]` bằng **chỉ số bắt đầu** dành cho bucket `b` trong mảng đích. Duyệt mảng nguồn **từ trái sang phải**:

```java
int digit = extractDigit(value);
destination[next[digit]++] = value;
```

Đây chỉ là **dòng minh họa**; `extractDigit` và hai mảng cần được khai báo trong cài đặt. Hai phần tử có cùng digit được ghi theo thứ tự chúng xuất hiện trong nguồn: phần tử thứ nhất chiếm vị trí trước, sau đó `next[digit]` tăng lên. Vậy lượt phân phối là **stable**.

Một cài đặt khác có thể dùng **tổng tiền tố là vị trí kết thúc** và duyệt từ **phải sang trái** để giữ ổn định. Hai kỹ thuật tương đương về mục tiêu nhưng **không được trộn hướng quét với quy ước con trỏ vị trí** mà không chứng minh lại.

## 6. Sắp xếp số nguyên có dấu: không dùng phép lấy chữ số một cách ngây thơ

Java `int` là số nguyên **32 bit có dấu**, từ `Integer.MIN_VALUE` đến `Integer.MAX_VALUE`. Nếu dùng `x % B` trực tiếp cho `x<0`, phần dư của Java có thể **âm**, không phải chỉ số bucket `0..B−1`. Việc chia/lấy trị tuyệt đối cũng không đủ: `Math.abs(Integer.MIN_VALUE)` vẫn là số âm vì giá trị tuyệt đối toán học không biểu diễn được trong `int`.

Một kỹ thuật đúng cho **LSD theo bit và thứ tự tăng dần số có dấu** là chuyển khóa bằng:

```java
int normalized = value ^ Integer.MIN_VALUE;
```

Phép XOR này **đảo bit dấu**:

- `Integer.MIN_VALUE` có khóa chuẩn hóa không dấu `0`.
- `−1` có khóa chuẩn hóa không dấu `2147483647`.
- `0` có khóa chuẩn hóa không dấu `2147483648`.
- `Integer.MAX_VALUE` có khóa chuẩn hóa không dấu `4294967295`.

Hai số cuối vượt phạm vi **int có dấu dương**, nhưng dãy 32 bit của chúng vẫn tồn tại trong kiểu `int`; các con số trên được hiểu **theo cách diễn giải không dấu**. Khi so sánh theo **giá trị không dấu của khóa đã chuẩn hóa**, thứ tự từ nhỏ đến lớn đúng với thứ tự `int` có dấu ban đầu.

Với cơ số `B=2^r`, chữ số bắt đầu ở bit `shift` được tính bằng:

```java
int mask = (1 << bitsPerDigit) - 1;
int digit = ((value ^ Integer.MIN_VALUE) >>> shift) & mask;
```

Ở đây `>>>` là **dịch phải không dấu**; `& mask` giữ đúng `r` bit của chữ số. Không dùng phép dịch phải có dấu `>>` nếu định dùng công thức này, vì các bit dấu mở rộng có thể làm sai khóa cao. Giới hạn `1≤r≤16` trong ví dụ giúp `B=1<<r` và `mask` vừa kiểu `int`, đồng thời mảng đếm có kích thước thực tế.

Các lượt lần lượt xử lý `shift=0,r,2r,...` cho đến khi `shift<32`. Lượt cuối có thể chỉ chứa một phần `r` bit (như `r=11`); toán tử `>>>` và mask vẫn trích đúng những bit còn lại. Không nên dịch `shift≥32` trên `int`, vì Java thực tế chỉ dùng năm bit thấp của lượng dịch, khiến `>>>32` tương đương `>>>0` chứ không phải trả 0.

## 7. LSD và MSD khác nhau ra sao?

Bài học về “số lượt phân phối” cần phân biệt hai hướng xử lý chữ số:

| Thuộc tính | **LSD** (thấp → cao) | **MSD** (cao → thấp) |
| --- | --- | --- |
| Thứ tự xử lý | Bắt đầu từ chữ số thấp nhất | Bắt đầu từ chữ số cao nhất |
| Phân phối | Thường thực hiện một lượt **toàn bộ mảng** cho mỗi chữ số | Phân phối theo chữ số cao nhất, rồi xử lý riêng từng bucket ở chữ số tiếp theo |
| Điều kiện quan trọng | Mỗi lượt phải **stable** để giữ thứ tự chữ số thấp đã xử lý | Cần xử lý đệ quy/riêng từng bucket đúng nghĩa; có thể có thiết kế dùng phân phối tại chỗ hoặc không stable nhưng phải bảo đảm thứ tự theo nhóm |
| Độ sâu/nhịp xử lý | Dãy lượt toàn cục thường biết trước từ độ dài khóa | Có thể khác nhau giữa bucket, nhất là với khóa độ dài không đều |
| Ví dụ thích hợp | Số nguyên độ dài cố định, khóa có số bit biết trước | Chuỗi/khóa biến độ dài, khi dễ phân nhánh theo tiền tố |

Công thức `d=ceil(w/r)` mô tả **số chữ số cần xem** cho khóa `w` bit; với LSD chuẩn, đó là số lượt qua toàn bộ dữ liệu. Với MSD, có thể có nhiều **lượt phân phối trên các nhóm nhỏ** ở cùng một độ sâu, nên không được tự hiểu `d` là tổng số lệnh phân phối được thực thi trên toàn bộ cây đệ quy.

Với chuỗi, việc chọn cơ số còn gắn với bảng chữ cái và quy tắc kết thúc chuỗi: chuỗi ngắn có thể cần **ký hiệu sentinel** đứng trước các ký tự thật để giữ thứ tự từ điển đúng. Không thể thay trực tiếp “số chữ số nguyên” bằng “độ dài chuỗi” mà bỏ qua việc căn chỉnh và so sánh độ dài.

## 8. Java 17+ — chọn r bit một chữ số và đếm số lượt

Chương trình sau triển khai LSD radix sort cho toàn bộ giá trị `int` có dấu bằng cách **đảo bit dấu trước khi trích chữ số**, dùng **counting sort ổn định** trong mỗi lượt, và cho phép chọn `bitsPerDigit` từ `1` đến `16`.

Để làm rõ ổn định, ví dụ còn có `Item(key,label)` và sắp theo `key` nhưng giữ thứ tự nhãn của những phần tử có khóa bằng nhau. Hai hàm dùng cùng công thức phân phối, một hàm cho `int[]` và một hàm cho mảng `Item[]`. Mỗi hàm trả **mảng mới** và không sửa mảng đầu vào.

Lưu file **RadixChoiceDemo.java**:

```java
import java.util.Arrays;

public class RadixChoiceDemo {
    record Item(int key, String label) {
        @Override
        public String toString() {
            return key + ":" + label;
        }
    }

    static int passes(int bitsPerDigit) {
        validateBits(bitsPerDigit);
        return (32 + bitsPerDigit - 1) / bitsPerDigit;
    }

    static void validateBits(int bitsPerDigit) {
        if (bitsPerDigit < 1 || bitsPerDigit > 16) {
            throw new IllegalArgumentException("bitsPerDigit must be 1..16");
        }
    }

    // Đảo bit dấu để thứ tự unsigned của khóa chuẩn hóa
    // đúng với thứ tự signed của int ban đầu.
    static int digit(int value, int shift, int mask) {
        return ((value ^ Integer.MIN_VALUE) >>> shift) & mask;
    }

    static int[] radixSort(int[] input, int bitsPerDigit) {
        validateBits(bitsPerDigit);
        int[] src = input.clone();
        if (src.length < 2) {
            return src;
        }

        int base = 1 << bitsPerDigit;
        int mask = base - 1;
        int[] next = new int[base];
        int[] dst = new int[src.length];

        for (int shift = 0; shift < 32; shift += bitsPerDigit) {
            Arrays.fill(next, 0);

            // Đếm số phần tử thuộc từng bucket.
            for (int value : src) {
                next[digit(value, shift, mask)]++;
            }

            // Chuyển số lượng thành vị trí bắt đầu bucket.
            int start = 0;
            for (int b = 0; b < base; b++) {
                int count = next[b];
                next[b] = start;
                start += count;
            }

            // Duyệt từ trái qua phải để phân phối ổn định.
            for (int value : src) {
                int b = digit(value, shift, mask);
                dst[next[b]++] = value;
            }

            // Mảng đích thành nguồn của lượt chữ số kế tiếp.
            int[] temp = src;
            src = dst;
            dst = temp;
        }
        return src;
    }

    static Item[] radixSortItems(Item[] input, int bitsPerDigit) {
        validateBits(bitsPerDigit);
        Item[] src = input.clone();
        if (src.length < 2) {
            return src;
        }

        int base = 1 << bitsPerDigit;
        int mask = base - 1;
        int[] next = new int[base];
        Item[] dst = new Item[src.length];

        for (int shift = 0; shift < 32; shift += bitsPerDigit) {
            Arrays.fill(next, 0);
            for (Item item : src) {
                next[digit(item.key(), shift, mask)]++;
            }

            int start = 0;
            for (int b = 0; b < base; b++) {
                int count = next[b];
                next[b] = start;
                start += count;
            }

            for (Item item : src) {
                int b = digit(item.key(), shift, mask);
                dst[next[b]++] = item;
            }

            Item[] temp = src;
            src = dst;
            dst = temp;
        }
        return src;
    }

    // Mọi mảng dài 0..5 lấy phần tử trong {-2,-1,0,1,2};
    // đối chiếu 3 cơ số với Arrays.sort trên 3906 input nhỏ.
    static int checkSmallCases() {
        int variations = 1;
        int checked = 0;

        for (int n = 0; n <= 5; n++) {
            for (int encoded = 0; encoded < variations; encoded++) {
                int[] input = new int[n];
                int code = encoded;
                for (int i = 0; i < n; i++) {
                    input[i] = code % 5 - 2;
                    code /= 5;
                }

                int[] expected = input.clone();
                Arrays.sort(expected);

                for (int bits : new int[]{4, 8, 11}) {
                    int[] actual = radixSort(input, bits);
                    if (!Arrays.equals(expected, actual)) {
                        throw new AssertionError(
                            "bits=" + bits
                            + ", input=" + Arrays.toString(input));
                    }
                }
                checked++;
            }
            variations *= 5;
        }
        return checked;
    }

    public static void main(String[] args) {
        int[] numbers = {
            170, -5, 75, 90, 802, 24, 2, 66, -5, 0,
            Integer.MIN_VALUE, Integer.MAX_VALUE
        };

        for (int bits : new int[]{4, 8, 11, 16}) {
            int[] sorted = radixSort(numbers, bits);
            System.out.println(
                "bits=" + bits
                + ", base=" + (1 << bits)
                + ", passes=" + passes(bits)
                + ": " + Arrays.toString(sorted));
        }

        System.out.println("Input unchanged: "
                           + Arrays.toString(numbers));

        Item[] tagged = {
            new Item(2, "A"), new Item(-1, "B"),
            new Item(2, "C"), new Item(-1, "D"),
            new Item(0, "E")
        };
        System.out.println(
            "Stable items: " + Arrays.toString(radixSortItems(tagged, 8)));
        System.out.println(
            "Empty: " + Arrays.toString(radixSort(new int[0], 8)));

        System.out.println(
            "Exhaustive small check: OK ("
            + checkSmallCases() + " arrays x 3 bases)");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 RadixChoiceDemo.java
java RadixChoiceDemo
```

Stdout:

```text
bits=4, base=16, passes=8: [-2147483648, -5, -5, 0, 2, 24, 66, 75, 90, 170, 802, 2147483647]
bits=8, base=256, passes=4: [-2147483648, -5, -5, 0, 2, 24, 66, 75, 90, 170, 802, 2147483647]
bits=11, base=2048, passes=3: [-2147483648, -5, -5, 0, 2, 24, 66, 75, 90, 170, 802, 2147483647]
bits=16, base=65536, passes=2: [-2147483648, -5, -5, 0, 2, 24, 66, 75, 90, 170, 802, 2147483647]
Input unchanged: [170, -5, 75, 90, 802, 24, 2, 66, -5, 0, -2147483648, 2147483647]
Stable items: [-1:B, -1:D, 0:E, 2:A, 2:C]
Empty: []
Exhaustive small check: OK (3906 arrays x 3 bases)
```

### Giải thích chương trình

- `passes(bitsPerDigit)` dùng phép chia nguyên làm tròn lên, nên `4→8` lượt, `8→4`, `11→3`, `16→2` đối với **32 bit**.
- `base` quyết định đúng kích thước `next`; `next` được xóa mỗi lượt để không mang số đếm cũ sang chữ số khác.
- Sau khi đếm, `next[b]` chuyển thành **vị trí đầu tiên của bucket b**, rồi tăng dần khi phân phối từ trái sang phải. Điều này bảo đảm **stable**, là điều kiện cốt lõi để LSD đúng.
- `src` và `dst` đổi vai sau mỗi lượt; phương thức trả tham chiếu đến **mảng cuối cùng** `src`. Cả hai mảng làm việc đều khác input vì `input.clone()` đã tạo bản sao.
- Giá trị âm và cực trị có thứ tự đúng do XOR bit dấu rồi dịch `>>>`; không lấy `Math.abs` và không dùng phần dư âm làm bucket.
- Mỗi `Item` mang `key` và `label`. Với hai phần tử cùng khóa `−1`, nhãn `B` vẫn trước `D`; với hai khóa `2`, nhãn `A` vẫn trước `C`. Đây là bằng chứng quan sát được cho **tính ổn định**.
- Hàm `checkSmallCases` thử đúng `1+5+25+125+625+3125=3.906` mảng đầu vào theo dãy giá trị, với ba lựa chọn `bits=4,8,11` (tổng **11.718 lần chạy radix**), đối chiếu với kết quả `Arrays.sort`. Phép thử giúp phát hiện lỗi, nhưng không thay cho chứng minh bất biến cho mọi khóa 32 bit.
- Mảng rỗng và một phần tử được trả về bản sao ngay, không cần cấp phát bucket. Hàm nhận `bitsPerDigit` ngoài `1..16` sẽ báo `IllegalArgumentException` trước khi xử lý.

**Về chi phí cấp phát:** Đối với `n≥2`, chương trình tạo `src` và `dst`, mỗi mảng chứa `n` phần tử, cùng `next` dài `B`; đó là `O(n+B)` bộ nhớ phụ. Có thể thiết kế biến thể đổi chỗ/thu hồi vùng nhớ, nhưng không được vì thế tuyên bố cài đặt này “in-place”. Với input rất nhỏ, `B=65536` có thể không hợp lý dù chỉ hai lượt; đó là ví dụ trực tiếp về đánh đổi cơ số.

## 9. Phân biệt radix sort với counting sort một lượt

**Counting sort** đếm trực tiếp từng **giá trị khóa** trong miền nhỏ `[min,max]`; nếu số khóa khả dĩ là `K`, có thể chạy trong `O(n+K)` thời gian và `O(n+K)` bộ nhớ với phân phối ổn định. Khi `K` nhỏ, một lượt theo toàn bộ khóa có thể tốt hơn nhiều lượt radix.

**Radix sort** tách khóa thành **chữ số**. Nếu miền giá trị rất lớn, ví dụ toàn bộ 32 bit, ta chỉ cần `B=256` bucket mỗi lượt và thực hiện `4` lượt. Điều này tránh mảng đếm kích thước `2^32` của counting sort trực tiếp.

Với giá trị âm, counting sort trực tiếp thường đổi chỉ số bucket thành `value−min`, nhưng cần tính hiệu bằng kiểu đủ rộng để tránh tràn. Với radix theo bit, ta dùng chuyển khóa `value ^ Integer.MIN_VALUE` và trích r bit, không cần biết `min` hay `max` của input.

### Khi nào số lượt có thể giảm?

Nếu tất cả khóa đều **không âm** và đầu vào đã biết bị chặn bởi một `U` nhỏ, có thể chỉ chạy `d` lượt đủ xử lý `U` (hoặc một lần counting sort trực tiếp). Nếu các khóa là số nguyên có dấu 32 bit và ta dùng kỹ thuật đảo bit dấu, việc tự bỏ lượt cao mà không có một chứng minh phù hợp **có thể phá thứ tự giữa số âm và không âm**.

Một tối ưu cẩn thận có thể tính **khóa chuẩn hóa lớn nhất theo thứ tự không dấu** rồi xác định số bit cao thực sự cần; nhưng nó thêm bước quét, cần xử lý trường hợp mọi khóa bằng nhau và không nên dùng phép so sánh `int` có dấu để tìm cực đại của các khóa chuẩn hóa. Bản ví dụ cố định lượt theo `w=32` để hợp đồng đúng dễ kiểm chứng trên toàn miền `int`.

## 10. Lỗi thường gặp khi chọn cơ số hoặc tính lượt

**1. Chọn cơ số lớn nhất có thể.** `B` lớn làm `d` giảm nhưng tạo mảng bucket lớn; xóa/tính prefix `O(B)` mỗi lượt có thể áp đảo chi phí `O(n)`, nhất là khi dữ liệu ít.

**2. Tính sai số lượt ở ranh giới.** `U=999` theo cơ số 10 cần ba chữ số; `U=1000` cần bốn. Với `w=32,r=11` phải làm **ba lượt** tại shift `0,11,22`, không phải hai. Lượt cuối dù chỉ có 10 bit vẫn cần xử lý.

**3. Dùng logarit số thực để kiểm số lượt mà bỏ qua sai số.** Với số nguyên, nên dùng phép chia lặp hoặc công thức số bit, tránh lệch ở lũy thừa `B`.

**4. Lấy digit âm bằng `value % base`.** Phần dư có thể âm; bucket âm gây lỗi truy cập, và thứ tự khóa có dấu cũng không tự được xử lý đúng.

**5. Dùng `Math.abs` để né âm.** `Math.abs(Integer.MIN_VALUE)` không cho giá trị dương trong `int`; đồng thời trị tuyệt đối không giữ nguyên thứ tự mong muốn của số âm.

**6. Quên ổn định ở mỗi lượt LSD.** Nếu bucket trả phần tử bằng digit theo thứ tự khác, các lượt chữ số cao có thể phá thứ tự các chữ số thấp; chứng minh LSD không còn đúng.

**7. Quên reset mảng đếm mỗi lượt.** Bucket ở lượt tiếp theo phải đếm lại trên digit khác. Dữ liệu còn sót làm vị trí phân phối sai, có thể ghi vượt mảng đích hoặc bỏ phần tử.

**8. Sai thứ tự prefix và scatter.** Với `next[b]` là **vị trí bắt đầu bucket**, phải phân phối từ **trái sang phải** để bảo đảm stable. Nếu dùng vị trí cuối bucket thì quy tắc quét phải đổi tương ứng.

**9. Coi `d` là toàn bộ chi phí.** Cần tính `O(B)` thiết lập bucket, `O(n)` đọc/ghi mỗi lượt, bộ nhớ đệm, và chi phí snapshot/copy input. Ít lượt không bảo đảm tổng thời gian thấp.

**10. Dịch bit không đúng.** Trong Java, `>>>` và `>>` khác nhau khi bit cao là 1; lượng dịch `int` từ 32 trở lên bị lấy modulo 32. Phải khống chế `shift<32` và dùng mask đúng `B−1`.

**11. Nhầm LSD với MSD.** LSD phân phối ổn định trên toàn dãy qua các chữ số từ thấp lên; MSD có phân phối theo nhóm đệ quy và quy tắc khác. Không sao chép công thức/chiến lược dừng giữa hai loại mà bỏ qua chứng minh.

**12. Áp dụng radix cho khóa không có biểu diễn thứ tự phù hợp.** Đối với chuỗi, số thực, khóa tổng hợp hoặc comparator tùy biến, cần xác định cách ánh xạ thành chữ số sao cho thứ tự từ điển của các chữ số **trùng khớp quan hệ so sánh mong muốn**. Không thể tự lấy bit thô của `float` rồi giả định thứ tự số học đúng, đặc biệt với số âm, NaN hay `−0.0`.

## 11. Bài tập thực hành

**Bài 1 — Tự tính số lượt.** Với `U=999999`, tính `d` cho `B=10`, `100`, `1000`. Nếu vẫn dùng counting sort ổn định với `B` bucket mỗi lượt, đánh giá chi phí `d(n+B)` cho `n=100` và `n=100000`.

*Gợi ý:* Lần lượt `6,3,2` lượt. Với `n=100`, việc tăng `B` có thể tốn hơn lợi ích giảm lượt.

**Bài 2 — Trace LSD cơ số 10.** Thực hiện ba lượt trên `[170,45,75,90,802,24,2,66]`; chỉ ra thứ tự các phần tử trùng digit phải được giữ ra sao, và vì sao sau lượt hàng trăm có thứ tự hoàn chỉnh.

**Bài 3 — Chọn nhóm bit.** Với `int` 32 bit, viết bảng `(r,B,d)` cho `r=4,8,11,16`, rồi nêu ưu/nhược về cache và mảng đếm. Cơ số nào tối ưu trên mọi máy? Giải thích.

**Bài 4 — Chứng minh ổn định.** Với prefix positions `next[b]` và vòng lặp nguồn từ trái sang phải, chứng minh hai phần tử cùng digit xuất hiện trong đích theo đúng thứ tự đầu vào. Từ đó quy nạp tính đúng của LSD.

**Bài 5 — Số có dấu.** Viết theo hex khóa chuẩn hóa của `Integer.MIN_VALUE`, `−1`, `0` và `Integer.MAX_VALUE`. Giải thích vì sao thứ tự khóa **không dấu** sau XOR `Integer.MIN_VALUE` tương ứng thứ tự số nguyên có dấu ban đầu.

*Gợi ý:* `0x00000000`, `0x7FFFFFFF`, `0x80000000`, `0xFFFFFFFF`.

**Bài 6 — Trường hợp biên shift.** Với `r=11`, xác định số bit hữu ích ở lượt `shift=22`. Vì sao vẫn cần lượt đó? Nếu sử dụng `>>>32` ở vòng lặp, Java sẽ làm gì?

**Bài 7 — So sánh với counting sort.** Có `n=1.000.000` số nguyên trong `[0,99]`. So sánh counting sort trực tiếp `K=100` bucket với radix sort cố định 32 bit sử dụng `B=256`; phương án nào tránh những lượt không cần thiết? Nêu điều kiện để kết luận.

**Bài 8 — Kiểm thử.** Sinh dữ liệu gồm mảng rỗng, một phần tử, toàn số bằng nhau, số âm, số dương, `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, các giá trị có nhiều chữ số giống nhau. Đối chiếu từng lựa chọn `r` với `Arrays.sort`, và dùng các nhãn đi kèm khóa trùng để kiểm tra tính ổn định.

## 12. Quy trình chọn cơ số cho một bài mới

1. **Xác định loại khóa và thứ tự mong muốn.** Dữ liệu là số nguyên không âm, số nguyên có dấu, chuỗi hay khóa khác? Có cần stable và giữ nguyên input không?
2. **Xác định miền/độ rộng khóa.** Có `U` hữu hạn đủ nhỏ hay phải hỗ trợ toàn bộ `w` bit? Nếu cố định bit, chọn `B=2^r` phù hợp thao tác dịch/mask.
3. **Tính số lượt bằng công thức đúng.** Với `U>0` không âm: `d=ceil(log_B(U+1))` (dùng tính toán số nguyên khi cài đặt); với `w` bit: `d=ceil(w/r)`.
4. **Tính chi phí cả một lượt.** Nếu counting sort ổn định có `B` bucket, dự toán `O(n+B)` mỗi lượt, `O(n+B)` bộ nhớ phụ; nhân với `d`.
5. **Chọn cơ số cân bằng bộ nhớ/cache và số lượt.** So sánh vài `r` khả thi trên dữ liệu đại diện; không mặc định `r` lớn nhất là nhanh nhất.
6. **Chứng minh đúng và stable.** Mỗi lượt phải giữ thứ tự cũ giữa phần tử cùng digit; sau `k` lượt dữ liệu sắp theo `k` chữ số thấp; cuối cùng đúng toàn khóa.
7. **Xử lý giới hạn và ngoại lệ.** Mảng rỗng, số trùng, số âm, dịch bit, dữ liệu dài ngắn khác nhau, điều kiện giữ input và chi phí output.
8. **Kiểm thử đối chiếu.** Chạy nhiều cơ số cho cùng input, so với thuật toán tham chiếu, kiểm chứng thứ tự nhãn trùng khóa và đo hiệu năng trên kích thước thực tế.

**Tiêu chí hoàn thành:** Bạn có thể giải thích **vì sao cơ số lớn làm ít lượt nhưng nhiều bucket**, tự tính `d` cho cả khóa giới hạn và khóa `w` bit, chứng minh vai trò ổn định của mỗi lượt LSD, lựa chọn `r` theo chi phí `d(n+B)`, và cài đặt Java 17+ đúng với số nguyên âm và giá trị biên.
