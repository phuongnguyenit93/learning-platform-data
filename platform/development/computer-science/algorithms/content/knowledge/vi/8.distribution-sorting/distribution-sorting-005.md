# Radix sort từ chữ số cao đến thấp

**MSD radix sort** (*Most Significant Digit radix sort*) là thuật toán **sắp xếp phân phối**: thay vì dùng phép so sánh trực tiếp giữa mọi cặp phần tử, nó xét lần lượt các **chữ số/đơn vị khóa từ vị trí có ý nghĩa cao nhất đến thấp nhất**, phân phần tử vào các nhóm (*buckets*) theo đơn vị đang xét, rồi **đệ quy sắp xếp riêng từng nhóm** ở vị trí kế tiếp.

Với số thập phân không âm, “chữ số cao nhất” là hàng lớn nhất (nghìn, trăm, chục, đơn vị...). Với chuỗi, đó là ký tự **bên trái nhất**. MSD đặc biệt phù hợp khi nhiều khóa chia sẻ tiền tố: một khi hai phần tử nằm ở **hai nhóm chữ số cao khác nhau**, thứ tự tương đối của chúng đã được xác định; không cần xét tiếp các chữ số thấp để so sánh hai nhóm ấy.

Bài học trình bày bản chất thuật toán, cách chia nhóm ổn định bằng counting distribution, xử lý số có độ dài khác nhau và chuỗi có tiền tố, bất biến/chứng minh, chi phí, khác biệt với LSD radix sort và ví dụ Java 17+ chạy được.

## 1. Mô hình: chữ số, cơ số và thứ tự ưu tiên

Xét dãy số nguyên không âm:

```text
[170, 45, 75, 90, 802, 24, 2, 66, 45, 0]
```

Nếu chọn biểu diễn số **ba chữ số** (đệm số 0 ở đầu cho số ngắn hơn), ta nhìn như sau:

```text
170   045   075   090   802   024   002   066   045   000
 ^     ^     ^     ^     ^     ^     ^     ^     ^     ^
hàng trăm -> hàng chục -> hàng đơn vị
```

MSD bắt đầu ở **hàng trăm**:

- Nhóm 0: 45, 75, 90, 24, 2, 66, 45, 0.
- Nhóm 1: 170.
- Nhóm 8: 802.

Các nhóm sắp theo thứ tự chữ số 0, 1, ..., 9. Vì bất kỳ số có hàng trăm 0 đều nhỏ hơn số có hàng trăm 1, ta có thể giải quyết thứ tự **giữa các nhóm ngay**. Nhưng nhóm 0 còn lẫn 45, 75, 90, 24, 2, 66..., nên phải xét tiếp **hàng chục bên trong chính nhóm 0**. Các nhóm con còn nhiều phần tử tiếp tục được phân theo hàng đơn vị.

**Cơ số R (radix/base):** Nếu dùng chữ số thập phân, R=10; chữ số có thể từ 0 đến 9. Nếu dùng byte nhị phân, R=256; đơn vị khóa là một byte 0..255. Với chuỗi chỉ gồm 'a'..'z', một bước có 26 ký tự hợp lệ **cộng một ký hiệu kết thúc chuỗi**.

Đặc trưng của MSD là: **xử lý chữ số cao trước, rồi đệ quy từng nhóm cùng tiền tố**. Không được gộp mọi phần tử lại để sắp đồng loạt theo chữ số tiếp theo mà bỏ qua ranh giới nhóm, vì như vậy có thể làm mất thứ tự đã được quyết định bởi chữ số cao.

## 2. Phân biệt MSD và LSD radix sort

| Tiêu chí | MSD: chữ số cao → thấp | LSD: chữ số thấp → cao |
| --- | --- | --- |
| Chữ số xem xét đầu tiên | Quan trọng nhất, ví dụ hàng trăm | Ít quan trọng nhất, ví dụ hàng đơn vị |
| Tổ chức các lượt | Phân nhóm rồi xử lý **đệ quy bên trong từng nhóm** | Thường quét toàn bộ dãy qua từng vị trí chữ số |
| Lý do bảo toàn thứ tự | Các nhóm chữ số cao không được trộn sau khi tạo | Mỗi lượt phân phối theo chữ số cao hơn phải **ổn định** để giữ thứ tự của chữ số thấp |
| Có thể dừng sớm theo nhóm? | Có: nhóm chỉ còn 0/1 phần tử không cần phân tiếp | Bản cơ bản vẫn qua đủ số vị trí chữ số |
| Chuỗi khác độ dài | Có thể dùng ký hiệu kết thúc đứng trước ký tự | Cần quy ước đệm/độ dài phù hợp để duy trì thứ tự mong muốn |
| Trường hợp phù hợp | Khóa có tiền tố, chuỗi, phân nhánh theo ký tự đầu | Khóa cố định độ dài, triển khai theo nhiều pass ổn định |

**Ví dụ gây nhầm:** Nếu sắp số theo chữ số cao nhất rồi lần tiếp theo **trộn tất cả số** để sắp hàng chục như một mẻ toàn cục, ta không còn thực hiện MSD đúng. Trong MSD, phải xử lý hàng chục **riêng cho từng bucket hàng trăm**; mỗi bucket là một đoạn liên tục trong mảng.

MSD và LSD đều có thể dùng **counting sort ổn định** cho từng lượt, nhưng mục tiêu của tính ổn định và cách quản lý nhóm khác nhau. MSD cũng có các hiện thực phân hoạch tại chỗ không ổn định; không phải mọi biến thể MSD đều tự động giữ thứ tự của phần tử cùng khóa.

## 3. Một lượt phân phối ổn định bằng bộ đếm

Giả sử đang xử lý đoạn nửa mở **[lo, hi)** theo một chữ số cụ thể và có R bucket (0..R-1). Để phân phối ổn định:

1. **Đếm** có bao nhiêu phần tử mang chữ số d vào `count[d]`.
2. **Tính vị trí bắt đầu** của bucket d bằng tổng số phần tử thuộc các bucket nhỏ hơn d:
   - `start[0]=0`.
   - `start[d]=count[0]+...+count[d-1]` khi d>0.
3. Tạo `next[d]=start[d]`, là vị trí trống tiếp theo của bucket d (tương đối với lo).
4. **Quét đầu vào từ trái sang phải**. Với phần tử có chữ số d, đặt vào `aux[lo + next[d]]` rồi tăng next[d].
5. Chép đoạn `aux[lo..hi)` trở lại `a[lo..hi)`.
6. Đệ quy từng bucket còn ít nhất hai phần tử, ở **vị trí chữ số kế tiếp**, trừ trường hợp khóa đã kết thúc.

Lúc này, mọi phần tử trong bucket d đứng liên tiếp, và mọi bucket d đứng trước bucket lớn hơn d. Tính **ổn định trong một lượt** đến từ việc quét trái → phải và cấp ô trống theo thứ tự tăng: hai phần tử cùng bucket giữ nguyên thứ tự tương đối của chúng.

Ví dụ lấy chữ số hàng trăm của `170, 45, 802, 24, 2`:

```text
hàng trăm:      1    0    8    0   0
count[0] = 3, count[1] = 1, count[8] = 1
start[0]=0, start[1]=3, start[8]=4

sau phân phối: [45, 24, 2 | 170 | 802]
                 bucket0    b1     b8
```

Nhóm 0 vẫn giữ **45 trước 24 trước 2**, như thứ tự trong dữ liệu đầu vào của nhóm đó. Sau này chính nhóm 0 tiếp tục được xét hàng chục.

**Không cần tạo 10 danh sách riêng:** Dùng một mảng phụ chung `aux`, mảng `count` và các vị trí bắt đầu bucket giúp các nhóm được xếp ngay vào **những đoạn liên tục**. Đây là cách triển khai tương đối tiết kiệm đối tượng cấp phát trong Java.

## 4. MSD cho số nguyên không âm với cơ số 10

Giả định tất cả giá trị nằm trong **[0, Integer.MAX_VALUE]**. Nếu max là giá trị lớn nhất, chọn `place` là lũy thừa 10 lớn nhất không vượt quá max, nhưng luôn cho `place=1` nếu max=0.

Chữ số hiện tại của một số x:

```text
digit(x, place) = (x / place) % 10

place = 100  -> lấy hàng trăm
place = 10   -> lấy hàng chục
place = 1    -> lấy hàng đơn vị
```

Ví dụ `x=45` và `place=100`: `(45/100)%10=0`, nghĩa là **tự coi các chữ số đầu thiếu là 0**. Không cần đổi số thành chuỗi rồi đệm ký tự 0. Với các số **không âm**, biểu diễn cùng độ rộng bằng các chữ số 0 đầu giữ đúng thứ tự giá trị.

Sau khi phân phối theo `place`, thuật toán đệ quy **mỗi bucket** theo `place/10`. Nếu `place=1`, mọi chữ số đã được xét xong; nếu bucket còn ≤1 phần tử, cũng không cần đệ quy tiếp.

**Lưu ý đặc biệt:** Vì thuật toán dùng phép chia lấy chữ số thập phân trực tiếp, **không dùng nguyên xi cho số âm**. Trong Java, số âm có quy tắc chia/lấy dư riêng, bucket có thể âm và không phản ánh thứ tự số có dấu. Để hỗ trợ int âm, một hướng đúng là dùng biểu diễn khóa nhị phân cố định và biến đổi khóa `key = value ^ Integer.MIN_VALUE`, sau đó xem key như chuỗi byte **không dấu** từ cao xuống thấp; cách đó ánh xạ thứ tự số có dấu vào thứ tự khóa không dấu. Một lựa chọn khác là chia nhóm âm/không âm có quy tắc đảo thứ tự độ lớn phần âm và xử lý `Integer.MIN_VALUE` cẩn thận. Mã số nguyên ở phần 9 chủ động **từ chối số âm**.

## 5. MSD cho chuỗi có độ dài khác nhau

Đối với chuỗi, vị trí chữ số cao nhất tương ứng **ký tự bên trái nhất**, rồi đến ký tự kế. Có một vấn đề rất quan trọng: **một chuỗi có thể kết thúc trước chuỗi khác**.

Ví dụ thứ tự từ điển mong muốn (trong tập chữ thường ASCII):

```text
""  <  "a"  <  "an"  <  "ann"  <  "b"
```

Nếu ở độ sâu d chuỗi đã hết ký tự, cần xem nó mang **ký hiệu kết thúc** nhỏ hơn mọi ký tự thực. Trong ví dụ Java, ta quy ước:

- Bucket **0** = kết thúc chuỗi tại độ sâu d.
- Bucket **1..26** = ký tự 'a'..'z' ở độ sâu d.
- Các chuỗi ở bucket 0 **không cần đệ quy** vì chúng không còn ký tự nào để xét.
- Bucket 1..26 có ít nhất hai phần tử mới được xử lý tại độ sâu d+1.

Khi xét `"a"` và `"an"`:

1. Ở d=0, cả hai có 'a', cùng bucket chữ cái 'a'.
2. Ở d=1, `"a"` đã kết thúc nên thuộc bucket 0; `"an"` có 'n' nên thuộc bucket 14.
3. Bucket 0 đứng trước bucket 'n', vì vậy `"a" < "an"` đúng thứ tự.

**Vì sao bắt buộc có sentinel?** Nếu không định nghĩa rõ trường hợp chuỗi hết sớm, code có thể truy cập ngoài chuỗi hoặc đặt sai thứ tự: chuỗi là **tiền tố** của chuỗi khác phải được sắp trước chuỗi dài hơn theo thứ tự từ điển thông dụng với cùng tiền tố.

**Giới hạn của ví dụ:** Mã chuỗi dưới đây chỉ chấp nhận ký tự **'a'..'z' ASCII** và cho phép chuỗi rỗng. Điều đó giúp R nhỏ và thứ tự rõ ràng. Không thể dùng y nguyên bucket 1..26 cho chữ hoa, dấu tiếng Việt, emoji, các ký tự Unicode hay so sánh theo quy tắc ngôn ngữ. Đối với Unicode/tiếng Việt, cần định nghĩa **khóa so sánh (collation key)** hoặc quy tắc sắp xếp thực tế rồi thiết kế cách phân bucket tương ứng; thứ tự điểm mã Unicode/UTF-16 không đồng nhất với thứ tự từ điển tiếng Việt.

## 6. Bất biến và chứng minh tính đúng

Một cách chứng minh MSD đúng là quy nạp theo **vị trí chữ số đang xét** và cấu trúc các đoạn bucket.

**Bất biến của bước phân phối:**

- Với mỗi bucket b, mọi phần tử trong đoạn bucket b có **cùng chữ số** tại vị trí hiện tại.
- Nếu b<c thì toàn bộ phần tử của bucket b đứng **trước** bucket c sau bước phân phối.
- Trong mỗi bucket, thứ tự tương đối ban đầu được giữ nếu phân phối ổn định.
- Tổng số phần tử của các bucket bằng số phần tử ban đầu; mỗi phần tử được chép **đúng một lần**.

**Cơ sở:** Khi không còn chữ số nào cần xét, hoặc đoạn chỉ có 0/1 phần tử, đoạn ấy đã được sắp theo toàn bộ phần khóa còn lại.

**Bước quy nạp:** Giả sử tất cả phần tử của đoạn đang xử lý có cùng tiền tố trước vị trí d. Phân phối theo chữ số ở d sẽ đưa mọi chữ số nhỏ hơn đứng trước chữ số lớn hơn. Vì **chữ số d có ưu tiên cao hơn mọi chữ số sau d**, không cần so sánh các phần tử thuộc hai bucket khác nhau: thứ tự giữa chúng đã đúng. Trong mỗi bucket cùng chữ số tại d, áp dụng đệ quy ở vị trí d+1 để sắp đúng phần hậu tố. Ghép các bucket theo thứ tự tăng sẽ cho cả đoạn sắp đúng.

**Giữ thứ tự khóa bằng nhau:** Với triển khai counting distribution ổn định, hai phần tử có toàn bộ khóa giống nhau sẽ luôn đi vào cùng bucket ở mọi mức và không đổi thứ tự tương đối. Trong mảng `int[]` hay `String[]`, hai giá trị giống nhau trông không phân biệt được; tính ổn định sẽ có ý nghĩa quan sát rõ hơn khi sắp **bản ghi mang khóa và ID phụ**. Một biến thể MSD dùng hoán đổi tại chỗ có thể **không ổn định** dù vẫn sắp đúng.

### Vì sao thuật toán kết thúc?

Với số nguyên không âm, mỗi lời gọi đệ quy giảm `place` từ `10^d` xuống `10^(d-1)` cho đến 1; chỉ có hữu hạn vị trí chữ số (int không âm có nhiều nhất 10 chữ số thập phân). Các bucket ở mỗi mức là các đoạn hữu hạn; lời gọi chỉ diễn ra khi bucket có ít nhất hai phần tử và còn chữ số để xét.

Với chuỗi, mỗi lần đệ quy tăng vị trí ký tự d lên 1. Một chuỗi có độ dài hữu hạn; khi hết chuỗi, nó đi vào bucket kết thúc 0 và **không tiếp tục đệ quy**. Vì các nhóm là hữu hạn và các nhánh chỉ đi sâu qua những ký tự hiện hữu, độ sâu tối đa liên quan đến độ dài chuỗi dài nhất. Vậy lời gọi đệ quy đều kết thúc về mặt thuật toán.

**Giới hạn thực thi Java:** Dù độ sâu hữu hạn về toán học, các chuỗi cực dài cùng tiền tố có thể khiến lời gọi đệ quy quá sâu và gây `StackOverflowError` trên JVM. Khi thiết kế hệ thống cần xử lý khóa rất dài, nên cân nhắc đệ quy giới hạn độ sâu, stack thủ công hoặc chiến lược lai.

## 7. Độ phức tạp và các trường hợp tối ưu

Đặt:

- n: số phần tử.
- R: số bucket ở một lượt.
- w: số vị trí chữ số tối đa cần xét (ví dụ ≤10 đối với `int` không âm ở cơ số 10; đối với chuỗi là độ dài tối đa).
- G: số lời gọi phân phối thực sự trên các nhóm có ≥2 phần tử.

Nếu một lời gọi xử lý m phần tử, **count + prefix + scatter + copy** có chi phí **O(m+R)**. Vậy tổng chi phí là:

```text
T = O(tổng kích thước các nhóm đã phân phối + R * G)
  <= O(n*w + R*G)
```

Mỗi phần tử chỉ nằm trong **một nhóm ở một độ sâu**, nên tổng số phần tử qua tất cả nhóm tại một độ sâu không vượt quá n. G phản ánh chi phí khởi tạo mảng đếm và duyệt bucket ở mỗi nhóm — đặc biệt đáng chú ý khi R rất lớn.

| Tình huống | Thời gian | Bộ nhớ |
| --- | --- | --- |
| Một lượt phân phối m phần tử theo R bucket | O(m+R) | O(m+R) nếu tính mảng phụ cho đoạn |
| MSD cho n số nguyên không âm, w chữ số, R=10 | O(nw + R G), với R=10 cố định thường viết O(nw) | Mảng phụ O(n) + bộ đếm/stack O(Rw) |
| MSD cho n chuỗi, độ dài tối đa w, R=27 cố định | O(nw + R G); có thể tiết kiệm lượt ở các nhóm một phần tử | Mảng phụ O(n) + bộ đếm/stack O(Rw) |
| Nhiều khóa phân biệt ngay ở chữ số đầu | Ít nhóm con cần đệ quy, có thể gần O(n+R) | Mảng phụ + bộ đếm |
| Nhiều khóa giống nhau có tiền tố rất dài | Phải đi sâu qua nhiều vị trí trước khi gặp ký hiệu kết thúc | Stack có thể sâu đến O(w) |

**Diễn giải:** Với R cố định nhỏ và w cố định (như tối đa 10 chữ số thập phân của int không âm), thời gian thường được xem là **tuyến tính theo n** trong mô hình phép toán và truy cập số nguyên O(1). Với khóa dài, w không phải hằng số: không được tùy tiện gọi thuật toán là O(n) mà bỏ qua chi phí đọc chữ số và đệ quy.

**So sánh với sắp xếp so sánh:** Các thuật toán dựa hoàn toàn vào phép so sánh có cận dưới Ω(n log n) trong trường hợp xấu nhất khi phải phân biệt n khóa tùy ý. Radix sort tận dụng **cấu trúc chữ số của khóa** và một tập chữ số hữu hạn, nên có thể nhanh hơn ở các miền khóa phù hợp; nhưng cần mảng phụ, biết cách trích chữ số và thường phát sinh nhiều lượt quét.

**Sự đánh đổi giữa LSD và MSD:** LSD thường đơn giản, lặp qua w lượt trên cả dãy và cần mỗi lượt ổn định; MSD có thể dừng sớm ở các bucket nhỏ, phù hợp tiền tố, nhưng triển khai phức tạp hơn do quản lý đoạn bucket, đệ quy và quy tắc kết thúc.

## 8. Các bước chọn và áp dụng MSD

1. **Xác định khóa sắp xếp và thứ tự:** Không âm hay có dấu? Chuỗi dùng ASCII, Unicode hay collation? Thứ tự tăng theo số hay theo ký tự?
2. **Xác định cơ số R và chữ số:** Thập phân R=10; byte R=256; ký tự cần cách ánh xạ hữu hạn và trường hợp kết thúc.
3. **Xác định chữ số cao nhất:** Với số không âm, lấy lũy thừa của R lớn nhất cần xét. Với chuỗi, bắt đầu từ vị trí 0.
4. **Chọn cơ chế phân phối:** Counting distribution ổn định với một mảng phụ là lựa chọn đơn giản để giữ nhóm liên tục. Dùng hoán đổi tại chỗ có thể tiết kiệm bộ nhớ nhưng không bảo đảm ổn định.
5. **Lưu ranh giới từng bucket:** Nhờ mảng start/count; không để đệ quy bucket này tác động ra ngoài đoạn của nó.
6. **Chỉ đệ quy nhóm còn ≥2 phần tử và còn ký tự/chữ số:** Nhóm 0 biểu thị hết chuỗi phải được bỏ qua.
7. **Kiểm tra bằng test:** dãy rỗng, một phần tử, toàn giá trị bằng nhau, nhiều số 0 đầu, số rất lớn, chuỗi rỗng, từ là tiền tố, khóa trùng, miền khóa không hợp lệ.

Không nên trộn **giá trị số** và **biểu diễn chuỗi** một cách vô ý. Ví dụ "10" đứng **trước** "2" theo thứ tự từ điển ký tự, nhưng **10 lớn hơn 2** theo thứ tự số. Với số nguyên, MSD phải coi các số có **cùng độ rộng chữ số** (đệm số 0 ở đầu về mặt ý nghĩa) hoặc dùng biểu diễn nhị phân cố định phù hợp; không sắp chuỗi "10" và "2" rồi gọi đó là sắp số.

## 9. Chương trình Java 17+ hoàn chỉnh

Chương trình minh họa **hai phiên bản MSD độc lập**:

- `sortNonnegativeIntegers` sắp `int[]` không âm bằng chữ số thập phân từ cao xuống thấp, tự chọn hàng cao nhất, tương đương đệm số 0 đầu.
- `sortLowercaseWords` sắp `String[]` chỉ gồm 'a'..'z' hoặc chuỗi rỗng, theo thứ tự từ điển; ký hiệu kết thúc chuỗi là bucket 0.

Cả hai dùng một **mảng phụ chung**, bộ đếm và vị trí bắt đầu của từng bucket. Các phép kiểm tra đầu vào chạy **trước khi bắt đầu thay đổi mảng**; trường hợp invalid sẽ ném `IllegalArgumentException` hoặc `NullPointerException` tùy đầu vào. Chương trình dùng kiểu và API cơ bản, chạy trên Java 17+.

Lưu file **`MsdRadixSortDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

public class MsdRadixSortDemo {
    // Base 10: chi chap nhan so nguyen khong am.
    public static void sortNonnegativeIntegers(int[] a) {
        Objects.requireNonNull(a, "array must not be null");

        int max = 0;
        for (int x : a) {
            if (x < 0) {
                throw new IllegalArgumentException("negative number: " + x);
            }
            if (x > max) {
                max = x;
            }
        }

        int place = 1;
        while (max / place >= 10) {
            place *= 10;
        }

        int[] aux = new int[a.length];
        msdIntegers(a, aux, 0, a.length, place);
    }

    // Chi xu ly doan nua mo [lo, hi).
    private static void msdIntegers(
            int[] a, int[] aux, int lo, int hi, int place) {
        if (hi - lo <= 1 || place == 0) {
            return;
        }

        final int radix = 10;
        int[] count = new int[radix];
        for (int i = lo; i < hi; i++) {
            int digit = (a[i] / place) % radix;
            count[digit]++;
        }

        int[] start = new int[radix];
        for (int d = 1; d < radix; d++) {
            start[d] = start[d - 1] + count[d - 1];
        }

        int[] next = start.clone();
        for (int i = lo; i < hi; i++) {
            int digit = (a[i] / place) % radix;
            aux[lo + next[digit]++] = a[i];
        }
        System.arraycopy(aux, lo, a, lo, hi - lo);

        if (place > 1) {
            for (int d = 0; d < radix; d++) {
                int from = lo + start[d];
                int to = from + count[d];
                if (to - from > 1) {
                    msdIntegers(a, aux, from, to, place / 10);
                }
            }
        }
    }

    // Chuoi: bucket 0 = het chuoi; bucket 1..26 = 'a'..'z'.
    private static int wordBucket(String s, int depth) {
        if (depth == s.length()) {
            return 0;
        }
        return s.charAt(depth) - 'a' + 1;
    }

    public static void sortLowercaseWords(String[] words) {
        Objects.requireNonNull(words, "array must not be null");
        for (String word : words) {
            Objects.requireNonNull(word, "word must not be null");
            for (int i = 0; i < word.length(); i++) {
                char c = word.charAt(i);
                if (c < 'a' || c > 'z') {
                    throw new IllegalArgumentException(
                            "only lowercase a-z: " + word);
                }
            }
        }
        String[] aux = new String[words.length];
        msdWords(words, aux, 0, words.length, 0);
    }

    // Chi xu ly doan [lo, hi) voi chung tien to truoc depth.
    private static void msdWords(
            String[] words, String[] aux, int lo, int hi, int depth) {
        if (hi - lo <= 1) {
            return;
        }

        final int buckets = 27;
        int[] count = new int[buckets];
        for (int i = lo; i < hi; i++) {
            count[wordBucket(words[i], depth)]++;
        }

        int[] start = new int[buckets];
        for (int b = 1; b < buckets; b++) {
            start[b] = start[b - 1] + count[b - 1];
        }

        int[] next = start.clone();
        for (int i = lo; i < hi; i++) {
            int bucket = wordBucket(words[i], depth);
            aux[lo + next[bucket]++] = words[i];
        }
        System.arraycopy(aux, lo, words, lo, hi - lo);

        // Khong de quy bucket 0 vi chuoi da ket thuc.
        for (int b = 1; b < buckets; b++) {
            int from = lo + start[b];
            int to = from + count[b];
            if (to - from > 1) {
                msdWords(words, aux, from, to, depth + 1);
            }
        }
    }

    public static void main(String[] args) {
        int[] numbers = {170, 45, 75, 90, 802, 24, 2, 66, 45, 0};
        sortNonnegativeIntegers(numbers);
        System.out.println("Numbers: " + Arrays.toString(numbers));

        int[] equal = {7, 7, 7, 7};
        sortNonnegativeIntegers(equal);
        System.out.println("Equal numbers: " + Arrays.toString(equal));

        int[] boundaries = {Integer.MAX_VALUE, 0, 1};
        sortNonnegativeIntegers(boundaries);
        System.out.println("Boundaries: " + Arrays.toString(boundaries));

        int[] emptyNumbers = {};
        sortNonnegativeIntegers(emptyNumbers);
        System.out.println("Empty numbers: " + Arrays.toString(emptyNumbers));

        String[] words = {"tea", "to", "a", "ten", "in",
                "inn", "", "tea", "i"};
        sortLowercaseWords(words);
        System.out.println("Words: " + Arrays.toString(words));

        String[] prefixes = {"an", "a", "ann", "", "an", "b"};
        sortLowercaseWords(prefixes);
        System.out.println("Prefixes: " + Arrays.toString(prefixes));

        String[] single = {"z"};
        sortLowercaseWords(single);
        System.out.println("Single word: " + Arrays.toString(single));
    }
}
```

Biên dịch và chạy:

```bash
javac MsdRadixSortDemo.java
java MsdRadixSortDemo
```

Stdout dự kiến chính xác:

```text
Numbers: [0, 2, 24, 45, 45, 66, 75, 90, 170, 802]
Equal numbers: [7, 7, 7, 7]
Boundaries: [0, 1, 2147483647]
Empty numbers: []
Words: [, a, i, in, inn, tea, tea, ten, to]
Prefixes: [, a, an, an, ann, b]
Single word: [z]
```

**Giải thích output:**

- Số 2 và 24 đứng trước 45 dù chúng có ít chữ số hơn, vì phép lấy chữ số cao **ngầm coi các chữ số đầu còn thiếu bằng 0**.
- Dãy hai số 45 xuất hiện hai lần; chúng không bị mất sau các lượt phân phối.
- `Integer.MAX_VALUE=2147483647` có 10 chữ số, giúp kiểm tra vòng chọn `place` không tràn int: `place` dừng ở 1.000.000.000.
- `Arrays.toString(String[])` hiển thị chuỗi rỗng thành một vị trí rỗng giữa dấu ngoặc và dấu phẩy, ví dụ `[, a, i]`. Đây là biểu diễn mặc định của Arrays.toString, không phải phần tử null.
- `"i"` đứng trước `"in"`, và `"in"` đứng trước `"inn"` vì **kết thúc chuỗi được xếp trước ký tự kế tiếp**.
- `"tea"` xuất hiện hai lần và cùng nằm trước `"ten"`; `"to"` đứng sau nhóm `"te..."` vì 'o' lớn hơn 'e'.
- Mảng rỗng và một phần tử đều trả về hợp lệ mà không cần phân phối.

### Tại sao cách cài đặt dùng mảng phụ?

Bộ đếm và vị trí bucket chỉ biết **số lượng** phần tử mang từng chữ số, không thể tự dời mọi phần tử vào đúng vị trí mà không có nguy cơ ghi đè các phần tử chưa đọc. Mảng `aux` giúp copy ổn định, rồi chép lại đoạn vừa xử lý. Mỗi nhóm con tái sử dụng **cùng mảng aux có độ dài n**, thay vì tạo một mảng phụ mới cho từng nhóm. Đổi lại, bộ đếm/start/next được cấp phát mới trong từng lời gọi đệ quy; trên một đường gọi, số lượng các bộ mảng này tỷ lệ với độ sâu đệ quy.

## 10. Lỗi thường gặp và cách tránh

1. **Sắp theo chữ số thấp sau khi đã gộp lại mọi bucket:** Làm mất thứ tự ưu tiên chữ số cao. MSD phải xử lý **từng bucket** trước khi ghép kết quả.
2. **Không dùng cùng độ rộng cho số:** Nếu xem số như chuỗi chữ số trực tiếp, "10" có thể đứng trước "2" dù 10 > 2. Phải đệm 0 đầu về mặt logic hoặc dùng khóa số cố định độ rộng.
3. **Không xử lý chữ số/chuỗi đã kết thúc:** Khi sắp chuỗi, từ ngắn là tiền tố của từ dài phải đứng trước; dùng sentinel 0 và không đệ quy bucket này.
4. **Đệ quy bucket kết thúc chuỗi:** Các chuỗi giống nhau đã hết ký tự, nhưng gọi tiếp vô hạn hoặc truy cập ngoài chuỗi nếu không dừng đúng.
5. **Trộn ranh giới đoạn [lo,hi) và [lo,hi]:** Mã Java dùng đoạn nửa mở, nên hi là phần tử sau cuối, và số phần tử là hi−lo.
6. **Làm mất phân phối ổn định:** Khi muốn bảo đảm ổn định, quét input từ trái sang phải và tăng ô trống tiếp theo của bucket; nếu dùng hoán đổi tùy ý thì không tự nhiên ổn định.
7. **Chép mảng phụ không đúng phạm vi:** Chỉ dùng `System.arraycopy(aux,lo,a,lo,hi-lo)` cho đoạn đang xử lý, không được ghi đè phần tử của các bucket khác.
8. **Sai công thức vị trí bucket:** `start[d]` là tổng số phần tử có chữ số **nhỏ hơn d**, không bao gồm chính count[d].
9. **Sắp số âm bằng cùng phép chia %10:** Trong Java, số âm có phần dư âm; lấy bucket không hợp lệ và thứ tự sai. Cần tiền xử lý/ánh xạ khóa đúng hoặc từ chối như mã mẫu.
10. **Dùng bucket rất lớn mà không tính phí:** Khởi tạo và quét R bucket ở mỗi nhóm tốn O(R). Với Unicode hoặc khóa lớn, cần cơ chế phân phối khác phù hợp.
11. **Kết luận MSD luôn nhanh hơn quicksort:** Kết quả còn phụ thuộc số chữ số w, alphabet, số nhóm, bộ nhớ phụ, hiệu năng cache và phân bố tiền tố.
12. **Giả định mọi radix sort đều ổn định:** Đây là đặc tính của **cách phân phối**. MSD có thể thực hiện bằng counting distribution ổn định hoặc bằng in-place partition không ổn định.
13. **Dùng `charAt` mà không xét Unicode:** Với Java, `char` là đơn vị UTF-16, không tự đại diện đúng cho mọi Unicode code point, càng không mô tả quy tắc sắp tiếng Việt.
14. **Bỏ qua giới hạn độ sâu với chuỗi rất dài:** Lời gọi đệ quy vẫn hữu hạn nhưng có thể vượt stack thực tế của JVM; cần cách triển khai thích hợp khi xử lý khóa dài bất thường.

## 11. Câu hỏi ôn tập có đáp án

**Câu 1.** Với dãy `[401, 12, 305, 39, 7]` và số được coi rộng ba chữ số, kết quả phân nhóm đầu theo hàng trăm là gì?

**Đáp án:** Hàng trăm của 401 là 4, của 12/39/7 là 0, của 305 là 3. Vậy sau lượt ổn định: `[12, 39, 7 | 305 | 401]`, tương ứng bucket 0, 3, 4. Sau đó nhóm bucket 0 còn cần xử lý hàng chục/đơn vị.

**Câu 2.** Vì sao sau khi phân theo chữ số cao nhất, không được trộn các nhóm để chạy một lượt sort hàng chục trên toàn mảng?

**Đáp án:** Chữ số cao có ưu tiên lớn hơn chữ số thấp. Trộn nhóm có thể đưa phần tử chữ số cao hơn đi trước/sau không đúng thứ tự số. MSD phải giữ các bucket chữ số cao riêng và chỉ xử lý hậu tố trong từng bucket.

**Câu 3.** Giữa chuỗi `"a"` và `"an"`, ký tự thứ hai được xử lý thế nào?

**Đáp án:** `"a"` đã hết nên vào bucket kết thúc 0; `"an"` có ký tự 'n' nên vào bucket 14. Bucket 0 đứng trước bucket 14, vì vậy "a" < "an".

**Câu 4.** Có 1.000 số int không âm, mỗi số tối đa 10 chữ số. Nếu dùng cơ số 10 cố định, độ phức tạp điển hình theo n là gì?

**Đáp án:** Mỗi phần tử được xử lý không quá w=10 mức; R=10 cũng cố định. Thời gian có thể mô tả O(nw), tức tuyến tính theo n khi w hằng. Tuy nhiên phần cấp phát/duyệt bucket và chi phí hệ thống vẫn ảnh hưởng hiệu năng thực.

**Câu 5.** Vì sao một lượt counting distribution ổn định không làm đảo thứ tự hai bản ghi thuộc cùng bucket?

**Đáp án:** Ta quét input từ trái sang phải và đưa mỗi bản ghi vào vị trí trống kế tiếp của bucket; bản ghi xuất hiện trước luôn nhận vị trí nhỏ hơn bản ghi cùng bucket xuất hiện sau.

**Câu 6.** Phần tử âm trong `int[]` có thể cho vào bucket bằng `(x/place)%10` của mã mẫu không?

**Đáp án:** Không. Số âm có thể sinh chữ số âm và thứ tự không tương thích với biểu diễn không dấu đã định nghĩa. Mã mẫu từ chối phần tử âm; muốn hỗ trợ cần thiết kế lại phép chuyển khóa (ví dụ XOR bit dấu cho biểu diễn khóa 32-bit không dấu).

**Câu 7.** Hai chuỗi giống nhau và đã kết thúc cùng ở vị trí d có cần đệ quy sâu hơn không?

**Đáp án:** Không. Chúng đều thuộc bucket sentinel 0; không còn chữ số để phân biệt. Cần **không đệ quy bucket 0** để kết thúc đúng.

**Câu 8.** Với chuỗi dài có chung tiền tố 10.000 ký tự, dù MSD chứng minh kết thúc, có cần quan tâm triển khai Java không?

**Đáp án:** Có. Đệ quy có thể rất sâu và gây StackOverflowError. Để hỗ trợ khóa dài, có thể dùng stack thủ công hoặc thuật toán lai giới hạn độ sâu.

## Ghi nhớ

MSD radix sort xét **chữ số/ký tự có ý nghĩa cao nhất trước**, phân phối ổn định thành các bucket theo chữ số đang xét, rồi **đệ quy riêng từng bucket** ở chữ số kế. Các bucket có chữ số cao khác nhau đã đúng thứ tự tương đối, không được trộn lại. Với số nguyên không âm, biểu diễn chữ số cố định độ rộng bằng 0 đầu bảo đảm thứ tự số; với chuỗi độ dài khác nhau, **ký hiệu kết thúc đứng trước mọi ký tự** bảo đảm từ ngắn đứng trước phần mở rộng của nó. Một lượt trên m phần tử và R bucket mất O(m+R); tổng thời gian phụ thuộc số chữ số được xử lý, số nhóm và chi phí bộ đếm, còn bộ nhớ có thêm mảng phụ cùng stack đệ quy.
