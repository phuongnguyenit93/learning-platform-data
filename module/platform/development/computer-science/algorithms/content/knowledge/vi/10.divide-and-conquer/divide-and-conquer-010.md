# Giảm chi phí kết hợp và tái sử dụng vùng nhớ

**Chia để trị** (*divide and conquer*) giải bài toán lớn bằng cách chia thành các bài toán con, giải từng phần rồi **kết hợp** (*combine*) kết quả. Nhiều lời giải chỉ chú ý đến cách chia và số lời gọi đệ quy mà bỏ qua hai chi phí quan trọng: **thao tác kết hợp có thể làm lặp công việc** và **cấp phát/sao chép vùng nhớ ở mỗi lời gọi có thể tạo lượng overhead lớn**.

Bài học này đưa ra một phương pháp tối ưu có kiểm chứng: phân tích chính xác phần kết hợp, bỏ những lần kết hợp không cần thiết, đưa công việc có thể gộp vào cùng một lượt, và **tái sử dụng một vùng nhớ phụ** cho toàn bộ cây đệ quy. Merge sort là ví dụ xuyên suốt vì bước trộn hai nửa có thứ tự làm rõ cả chi phí thời gian lẫn bộ nhớ. Một chương trình Java 17+ cuối bài minh họa sắp xếp ổn định, bỏ qua lượt trộn khi hai nửa đã đúng thứ tự, dùng chung buffer và **đếm cặp nghịch thế ngay khi trộn**.

## 1. Phần kết hợp nằm ở đâu trong chia để trị?

Một lời giải chia để trị thường có ba bước:

1. **Divide:** Chia đầu vào thành những phần nhỏ hơn.
2. **Conquer:** Giải các bài toán con; thông thường gọi đệ quy.
3. **Combine:** Kết hợp lời giải con thành lời giải cho toàn bộ đầu vào.

Có thể mô tả tổng thời gian bằng một hệ thức:

```text
T(n) = a * T(n/b) + D(n) + C(n)

a    = số bài toán con được giải
n/b  = kích thước xấp xỉ của mỗi bài toán con
D(n) = chi phí chia và quản lý
C(n) = chi phí kết hợp
```

Đây là **mô hình** cho trường hợp các bài toán con có kích thước gần nhau, không phải công thức áp dụng máy móc cho mọi đệ quy. Ví dụ quicksort có kích thước hai phía phụ thuộc pivot; phân hoạch là công việc ở mức hiện tại và kết hợp gần như không cần làm gì. Merge sort chia đôi đơn giản nhưng phải **trộn** hai phần đã sắp.

Với merge sort, chia chỉ số là O(1), mỗi nửa có kích thước gần n/2 và trộn hai nửa có tổng n phần tử trong O(n):

```text
T(n) = 2T(n/2) + Θ(n)
     = Θ(n log n)          (n > 1, làm tròn khi cần)
```

Nếu làm phần kết hợp một cách ngây thơ, ví dụ mỗi lần trộn phải **quét lại một nửa nhiều lần** hoặc dùng hai vòng lặp lồng nhau trên hai nửa, chi phí kết hợp có thể tăng lên Θ(n²). Khi đó:

```text
T(n) = 2T(n/2) + Θ(n²) = Θ(n²)
```

Ngược lại, trong một bài toán chỉ cần tổng hợp giá trị vô hướng từ hai lời giải con, phần kết hợp có thể chỉ O(1); với hai bài toán con kích thước n/2, hệ thức kiểu `2T(n/2)+O(1)` cho thời gian O(n). Vì vậy trước khi tối ưu cú pháp vòng lặp, phải hỏi: **Combine đang làm bao nhiêu công việc ở mỗi nút?** và **công việc nào thực sự cần thiết?**

## 2. Phân biệt ba loại chi phí thường bị gộp làm một

Trong một chương trình thực tế, thao tác kết hợp có thể tốn:

- **Phép toán xử lý dữ liệu:** so sánh, cộng dồn, trộn, cập nhật cấu trúc dữ liệu.
- **Di chuyển dữ liệu:** sao chép mảng, tạo mảng con, đóng gói đối tượng, ghi lại phần tử giữa các bộ đệm.
- **Quản lý vùng nhớ:** cấp phát, khởi tạo bộ nhớ, tạo nhiều đối tượng ngắn hạn, áp lực thu gom rác (*garbage collection*), hiệu ứng bộ nhớ đệm CPU.

Không phải mọi cải tiến đều thay đổi Big O.

**Ví dụ:** Merge sort dùng bộ đệm mới ở mỗi lần trộn và merge sort dùng một bộ đệm chung đều có thể mất **Θ(n log n)** phép so sánh/di chuyển dữ liệu ở trường hợp tổng quát. Nhưng phiên bản dùng chung buffer giảm số lần gọi `new`, giảm tổng lượng bộ nhớ được cấp phát tạm và giúp chương trình có đặc tính sử dụng bộ nhớ dễ dự đoán hơn.

Ngược lại, nếu bỏ hẳn một vòng lặp lồng nhau làm chi phí một lượt kết hợp từ O(n²) xuống O(n), ta có thể **thay đổi cả độ phức tạp tổng thể**. Đừng quảng cáo “giảm từ O(n log n) xuống O(n)” chỉ vì chuyển buffer từ trong hàm trộn ra ngoài nếu lượng công việc trộn thực chất không đổi.

### Một bảng câu hỏi khi đánh giá combine

| Câu hỏi | Tác dụng |
| --- | --- |
| Ở kích thước m, một lần combine duyệt bao nhiêu phần tử? | Ước lượng C(m) |
| Có phần tử nào bị đọc/ghi nhiều lần vô ích không? | Nhận diện sao chép hoặc quét lặp |
| Có thể duy trì một thống kê trong lúc kết hợp không? | Gộp nhiều pass thành một |
| Kết quả hai nửa đã thỏa điều kiện thứ tự chưa? | Có thể bỏ qua combine |
| Buffer được cấp phát ở đâu và bao nhiêu lần? | Phân biệt dung lượng đang dùng với tổng lượng cấp phát |
| Các lời gọi có thể dùng chung vùng nhớ hay đang chạy song song? | Xác định ownership, tránh ghi đè/race |

## 3. Ví dụ cơ bản: trộn hai đoạn đã có thứ tự

Giả sử mảng `a` có hai đoạn **nửa mở**:

- Đoạn trái `[lo, mid)` đã sắp tăng không giảm.
- Đoạn phải `[mid, hi)` đã sắp tăng không giảm.

Một bước trộn dùng hai con trỏ `i=lo`, `j=mid` và một vị trí ghi `k=lo`. Ở mỗi bước, so sánh hai đầu chưa xử lý; lấy phần tử nhỏ hơn rồi tiến con trỏ của phía tương ứng.

Ví dụ:

```text
Trái: [1, 4, 8]      Phải: [2, 3, 7]

Lấy 1 (trái), 2 (phải), 3 (phải),
4 (trái), 7 (phải), 8 (trái)

Sau trộn: [1, 2, 3, 4, 7, 8]
```

Vì mỗi lần ghi lấy **đúng một phần tử** và tiến một con trỏ, trộn m phần tử mất **Θ(m)** trong mô hình mảng thông thường. Không cần so sánh lại mọi cặp phần tử của hai nửa.

**Tính ổn định:** Nếu hai đầu có giá trị bằng nhau, ưu tiên phần tử của **nửa trái** (điều kiện `left <= right`). Nếu mỗi nửa đã giữ thứ tự tương đối của bản ghi đồng khóa, bước merge này cũng giữ thứ tự tương đối đó. Trong ví dụ mã mảng `int[]`, hai số bằng nhau nhìn không phân biệt được; tính ổn định quan trọng khi các phần tử là bản ghi có khóa và thông tin phụ.

### Vì sao trộn trực tiếp vào cùng mảng khó?

Nếu ghi ngay vào phần đầu `a` khi vẫn đang đọc hai nửa trên chính mảng đó, ta có thể **ghi đè một phần tử chưa đọc** ở phía phải/trái. Cách đơn giản, an toàn là đọc từ **mảng phụ chứa bản sao của đoạn** rồi ghi vào mảng chính.

Ví dụ mã khái niệm:

```java
System.arraycopy(a, lo, aux, lo, hi - lo);
int i = lo;
int j = mid;

for (int k = lo; k < hi; k++) {
    if (i >= mid) {
        a[k] = aux[j++];
    } else if (j >= hi) {
        a[k] = aux[i++];
    } else if (aux[i] <= aux[j]) {
        a[k] = aux[i++];
    } else {
        a[k] = aux[j++];
    }
}
```

Đoạn trên giả định **aux đã được cấp phát đủ kích thước và dùng cho đoạn [lo,hi)**. Nó không phải chương trình Java độc lập; chương trình chạy được ở phần 9.

## 4. Tối ưu thứ nhất: tái sử dụng một mảng phụ

### Cách kém hiệu quả: cấp phát ở mỗi lời gọi

Một cách viết phổ biến là tạo các mảng con của nửa trái và nửa phải bằng `Arrays.copyOfRange` ở mọi mức đệ quy, rồi tạo thêm mảng kết quả khi trộn. Chương trình vẫn có thể đúng nhưng mỗi mức phải tạo nhiều mảng tạm và sao chép dữ liệu.

Với n phần tử:

- Cây chia đôi có khoảng **n−1 nút kết hợp** (khi đến từng phần tử).
- Nếu mỗi nút tạo ít nhất một mảng tạm, số **lượt cấp phát** có thể lên đến Θ(n).
- Tổng độ dài các mảng/bản sao được cấp phát qua mọi mức có thể là **Θ(n log n)** ở cách hiện thực điển hình.
- **Dung lượng sống đồng thời** và **đỉnh sử dụng bộ nhớ** phụ thuộc thời điểm giải phóng, số mảng được giữ trên stack và cơ chế runtime; không được tự đồng nhất “tổng cấp phát Θ(n log n)” với “peak memory Θ(n log n)”.

Tạo nhiều mảng nhỏ có thể làm tăng chi phí cấp phát, khởi tạo, quản lý đối tượng và GC trên JVM. Dù không phải lúc nào cũng làm chậm đáng kể, đây là chi phí có thể loại bỏ rõ ràng.

### Cách nên dùng: cấp phát một lần

Tổ chức hàm theo hai lớp:

```text
sort(a):
    aux = new array of length a.length
    mergeSort(a, aux, 0, a.length)

mergeSort(a, aux, lo, hi):
    sort left half (reuse aux)
    sort right half (reuse aux)
    merge current segment using aux[lo .. hi)
```

**Tính chất chính:**

- Chỉ có **một mảng aux có chiều dài n** cho toàn bộ quá trình sắp xếp.
- Các lời gọi đệ quy chỉ truyền **tham chiếu tới cùng một mảng** cùng biên `lo, mid, hi`; không copy các nửa ra mảng mới.
- Các lời gọi diễn ra **tuần tự**; khi trộn đoạn cha, các lời gọi trộn ở hai con đã kết thúc. Vì vậy vùng aux được dùng lại an toàn theo thời điểm.
- Trong một lượt trộn, mọi thao tác đọc dữ liệu từ aux[lo..hi) sau khi sao chép từ a, và ghi vào a[lo..hi).
- Phần tử **ngoài đoạn hiện tại** không được sửa.

Ở đây, “tái sử dụng” có nghĩa là **tái sử dụng dung lượng**, không có nghĩa bỏ bớt các phép ghi/copy cần thiết của trộn. Tổng thời gian merge sort vẫn O(n log n) ở trường hợp tổng quát; không gian phụ cho aux giảm về **O(n)** với một buffer.

### Một buffer cho nhiều lần gọi hàm từ bên ngoài?

Nếu một dịch vụ thực hiện nhiều lượt sort liên tiếp, có thể tái sử dụng workspace giữa các lần gọi để giảm cấp phát hơn nữa, nhưng phải xác định **chủ sở hữu và vòng đời vùng nhớ**. Không nên dùng một mảng `static` dùng chung không đồng bộ cho nhiều luồng: hai lời gọi đồng thời có thể ghi đè dữ liệu của nhau. Có thể cấp buffer cho từng tác vụ hoặc dùng pool có cơ chế cấp phát/hoàn trả và giới hạn dung lượng rõ ràng.

Trong mã cuối bài, buffer được tạo đúng **một lần cho mỗi thao tác phân tích**, không có trạng thái tĩnh dùng chung và không làm thay đổi input.

## 5. Tối ưu thứ hai: bỏ lượt trộn khi đã có thứ tự

Sau khi hai nửa đã được sắp tăng, ta biết:

```text
a[lo .. mid)   đã sắp tăng
a[mid .. hi)   đã sắp tăng
```

Nếu **phần tử cuối của nửa trái không lớn hơn phần tử đầu của nửa phải**:

```text
a[mid - 1] <= a[mid]
```

thì **cả đoạn [lo,hi) đã sắp đúng thứ tự**. Khi đó không cần gọi merge, không cần `System.arraycopy` và không cần đọc/ghi toàn đoạn lần nữa.

```java
mergeSort(a, aux, lo, mid);
mergeSort(a, aux, mid, hi);

// Chỉ khi hai nửa không tự ghép thành thứ tự tăng:
if (a[mid - 1] <= a[mid]) {
    return; // Bỏ lượt merge
}
merge(a, aux, lo, mid, hi);
```

Điều kiện này an toàn vì cả hai nửa đã **được đảm bảo sắp xếp** trước khi kiểm tra. Không thể dùng nó khi chưa bảo đảm tính đúng của hai lời gọi con; chỉ so sánh hai giá trị biên của **hai đoạn chưa có thứ tự** là không đủ.

**Ví dụ bỏ lượt trộn:**

```text
Trái đã sắp: [1, 2, 3]    Phải đã sắp: [4, 5, 6]
a[mid-1] = 3 <= a[mid] = 4
=> [1, 2, 3, 4, 5, 6] đã sắp, không cần copy/merge.
```

Với đầu vào vốn đã được sắp tăng, **mọi nút kết hợp** trong cây merge sort có thể bỏ merge, chỉ làm một phép so sánh biên. Cây có O(n) nút, nên phiên bản này có thể chạy **O(n)** thời gian trên dữ liệu đã sắp sẵn (bao gồm sao chép đầu vào một lần nếu API giữ nguyên dữ liệu gốc), thay vì thực hiện O(n log n) di chuyển phần tử. Trường hợp tổng quát/xấu nhất vẫn **O(n log n)**.

Nếu hai biên **bằng nhau**, dùng điều kiện `<=` vẫn an toàn và ổn định: nửa trái được giữ trước nửa phải trong đoạn đã ghép. Dùng `<` cũng đúng về thứ tự nhưng có thể làm trộn không cần thiết trên dữ liệu có nhiều bản sao.

### Khi nào tối ưu bỏ merge không giúp?

Ví dụ `[9, 7, 5, 3, 1]` ngược thứ tự: ở nhiều nút, giá trị lớn nhất của nửa trái vượt quá giá trị nhỏ nhất của nửa phải, nên phải trộn thật sự. Điều kiện chỉ bổ sung O(1) phép so sánh ở mỗi nút, đổi lại có thể tiết kiệm nhiều phép copy trên đầu vào có thứ tự hoặc gần có thứ tự.

## 6. Tối ưu thứ ba: gộp tính toán vào ngay lúc merge

Nhiều bài chia để trị không chỉ muốn sắp mà còn cần **thống kê quan hệ giữa hai nửa**. Nếu làm một lượt merge rồi lại quét các cặp phần tử để thống kê, ta có thể tạo chi phí lớn. Có thể tận dụng việc **hai nửa đã được sắp** để tính toán trực tiếp trong lúc merge.

Ví dụ **cặp nghịch thế** (*inversion*): hai chỉ số i<j sao cho `a[i] > a[j]` trong mảng đầu vào gốc. Số cặp nghịch thế đo mức “chưa có thứ tự” của dãy.

Với mảng:

```text
a = [3, 1, 2]
Các nghịch thế: (3,1), (3,2)
Tổng = 2
```

Ta tách cặp nghịch thế thành:

1. Cặp nằm hoàn toàn trong nửa trái.
2. Cặp nằm hoàn toàn trong nửa phải.
3. **Cặp chéo**, một phần tử thuộc nửa trái, một phần tử thuộc nửa phải.

Hai loại đầu được đếm đệ quy. Loại chéo được đếm trong khi trộn **hai nửa đã sắp**.

Giả sử con trỏ i đang ở nửa trái và j ở nửa phải:

- Nếu `aux[i] <= aux[j]`, chọn aux[i] vào output; không có nghịch thế chéo nào giữa phần tử ấy với các phần tử chưa xét bên phải.
- Nếu `aux[i] > aux[j]`, chọn aux[j] trước. Vì nửa trái đã sắp tăng, **tất cả `mid-i` phần tử còn lại ở nửa trái đều lớn hơn aux[j]**. Ta cộng thẳng `mid-i` vào bộ đếm; không cần duyệt từng cặp.

Minh họa:

```text
Trái đã sắp: [2, 5, 8]        Phải đã sắp: [3, 7]

i trỏ 2, j trỏ 3: chọn 2, không cộng.
i trỏ 5, j trỏ 3: chọn 3, cộng 2 nghịch thế
                 (5,3) và (8,3).
i trỏ 5, j trỏ 7: chọn 5, không cộng.
i trỏ 8, j trỏ 7: chọn 7, cộng 1 nghịch thế (8,7).
Tổng nghịch thế chéo = 3.
```

Việc đếm này chỉ thêm **O(1)** thao tác cho mỗi lần chọn phần tử trong merge, nên vẫn **O(n log n)** tổng thể. Cách ngây thơ so sánh mọi cặp i<j để đếm có **O(n²)** thời gian.

**Tương thích với bỏ merge:** Nếu hai nửa đã có thứ tự và `a[mid-1] <= a[mid]`, thì **mọi giá trị ở nửa trái đều ≤ mọi giá trị ở nửa phải**. Do đó có **0 nghịch thế chéo** và có thể bỏ combine, vừa giữ đúng kết quả sort vừa giữ đúng kết quả đếm. Số nghịch thế đã đếm trong từng nửa vẫn được giữ nguyên.

**Lưu số đếm bằng long:** Với n phần tử, số nghịch thế có thể lên tới `n(n−1)/2`, vượt giới hạn `int` khi n đủ lớn. Trong Java, dùng `long` cho tổng; không lấy hiệu hai giá trị int để so sánh vì có thể tràn.

## 7. Chứng minh tính đúng của giải pháp tái sử dụng buffer

Một lời giải merge sort có tối ưu cần chứng minh cả **đầu ra** lẫn **sự an toàn khi dùng lại vùng nhớ**.

### Bất biến của merge

Giả sử `aux[lo..mid)` và `aux[mid..hi)` đã sắp. Ở đầu mỗi lần ghi vị trí k:

- `a[lo..k)` chứa **k−lo giá trị nhỏ nhất** trong hợp hai nửa, ở thứ tự tăng không giảm.
- `i` và `j` trỏ tới hai phần tử đầu tiên **chưa dùng** của nửa trái và phải.
- Mỗi phần tử trong hai nửa sẽ được đọc và ghi **chính xác một lần** tại một lượt merge.
- Hai phần có khóa bằng nhau được lấy từ nửa trái trước (đảm bảo ổn định).

**Khởi tạo:** k=lo, output rỗng, i=lo và j=mid nên bất biến đúng.

**Duy trì:** Phần tử nhỏ nhất chưa dùng là một trong hai đầu đang xét. Chọn đầu nhỏ hơn (hoặc đầu trái khi bằng) rồi tăng đúng một con trỏ. Output vẫn tăng và chứa đúng các phần tử nhỏ nhất đã lấy.

**Kết thúc:** Sau `hi−lo` lượt, tất cả phần tử của cả hai nửa đều đã được chọn, do đó a[lo..hi) là hợp đa tập đầy đủ, sắp tăng và ổn định.

### Vì sao reuse aux không làm mất dữ liệu?

Trước **mỗi lượt merge**, chương trình thực hiện:

```java
System.arraycopy(a, lo, aux, lo, hi - lo);
```

Từ thời điểm đó đến hết merge, mọi phép **đọc dữ liệu gốc của đoạn** diễn ra trên aux, trong khi mọi phép **ghi kết quả** diễn ra trên a. Vì thế ghi a[k] không thể phá dữ liệu chưa đọc từ aux. Các lời gọi con đã kết thúc trước khi cha gọi merge, nên việc cha ghi đè vào vùng aux đã được dùng bởi con là **hợp lệ**.

Sự tái sử dụng ở đây dựa trên **thứ tự thực thi tuần tự và phạm vi đoạn**. Nếu làm đồng thời hai lời gọi merge có đoạn aux **chồng lấn**, sẽ có race; không được sao chép nguyên thiết kế tuần tự cho hệ thống song song mà thiếu quản lý quyền sử dụng bộ nhớ.

### Quy nạp theo đoạn

- **Cơ sở:** Đoạn 0 hoặc 1 phần tử đã sắp sẵn, số nghịch thế 0.
- **Bước quy nạp:** Hai nửa được sắp đúng và đếm đúng nghịch thế bên trong bởi giả thiết quy nạp. Nếu biên thỏa `a[mid-1] <= a[mid]`, cả đoạn đã có thứ tự và không có nghịch thế chéo. Nếu không, trộn theo bất biến trên cho đầu ra đúng và cộng chính xác mọi nghịch thế chéo. Cộng cả ba loại nghịch thế được số đếm chính xác của đoạn.
- **Kết luận:** Lời gọi cho đoạn toàn mảng tạo bản sao đã sắp tăng, và trả chính xác số nghịch thế trong dữ liệu ban đầu.

### Chứng minh kết thúc

Mỗi lời gọi đệ quy trên đoạn dài m>1 chia thành hai đoạn có độ dài nhỏ hơn m. Số phần tử tại lá là 0 hoặc 1. Vòng trộn nếu chạy tăng k mỗi lượt, giới hạn bởi hi; mỗi bước tiêu thụ một phần tử. Bài toán có kích thước giảm nghiêm ngặt, nên thuật toán dừng.

## 8. Chi phí thời gian và bộ nhớ sau tối ưu

Giả sử n≥1 và thao tác so sánh/ghi phần tử int mất O(1):

| Thành phần | Thời gian | Không gian |
| --- | --- | --- |
| Sao chép input để bảo toàn mảng gốc | O(n) | O(n) cho bản sao |
| Cấp phát `aux` một lần | O(n) để cấp/khởi tạo trong mô hình mảng | O(n) |
| Hai lời gọi merge sort con | 2T(n/2) xấp xỉ | Đệ quy O(log n) stack |
| Kiểm tra `a[mid−1] <= a[mid]` | O(1) mỗi nút | O(1) |
| Một merge thực sự, đoạn dài m | Θ(m) | Dùng lại `aux` |
| Đếm nghịch thế chéo đồng thời merge | O(1) thêm mỗi lần chọn | O(1) biến đếm |
| **Trường hợp xấu/tổng quát** | **O(n log n)** | **O(n)** tổng dung lượng phụ |
| **Đầu vào đã sắp** | **O(n)** cho bản sao, khởi tạo và các kiểm tra nút | O(n) |

**Hai mảng độ dài n vẫn là O(n) bộ nhớ**, không phải O(n²): mã minh họa có `work=input.clone()` và `aux=new int[n]`, cộng O(log n) stack, nên tổng O(n). Nếu API cho phép **sửa trực tiếp input**, có thể bỏ mảng clone và chỉ giữ aux n phần tử (vẫn O(n)).

Nếu mục tiêu là **chỉ sắp tăng** không cần đếm nghịch thế, có thể bỏ bộ đếm long và mọi lệnh cộng nghịch thế, nhưng cấu trúc merge với buffer dùng lại vẫn giống nhau.

### Không gian *đang dùng* khác tổng *đã cấp phát*

Giả sử mã cũ tạo mảng tạm mỗi lần merge. Tổng số ô mảng được xin cấp qua toàn bộ đời thuật toán có thể là Θ(n log n), nhưng các mảng tạm có thể được giải phóng sau mỗi lời gọi. Do đó **tổng lượng cấp phát theo thời gian** và **mức bộ nhớ đỉnh** không phải một. Cách dùng một aux dài n loại bỏ nhiều lần cấp phát, nhưng không có nghĩa số byte thực sự ghi/đọc trong mọi merge đều giảm từ Θ(n log n) xuống O(n).

Với dãy đã sắp, **bỏ merge** mới là tối ưu có thể giảm **cả số phép di chuyển phần tử trên dữ liệu cụ thể đó**. Nếu không có điều kiện bỏ merge, chia để trị vẫn chạy đầy đủ các bước trộn ngay cả khi hai nửa đã ở đúng thứ tự.

## 9. Chương trình Java 17+ hoàn chỉnh

Chương trình tạo bản sao input, dùng **một mảng aux duy nhất** cho mọi lượt trộn, đồng thời tính số nghịch thế và đếm số lượt combine **thực sự trộn** / **được bỏ qua**. Số liệu này cho thấy khi input đã có thứ tự, nhiều lượt merge không cần thiết đã được loại bỏ.

Lưu tệp **`MergeWorkspaceReuse.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

public class MergeWorkspaceReuse {
    record Report(int[] sorted, long inversions, int merges, int skipped) {}

    private static final class Counters {
        long inversions;
        int merges;
        int skipped;
    }

    public static Report analyze(int[] input) {
        Objects.requireNonNull(input, "input must not be null");

        int[] work = input.clone();       // Khong sua input cua caller
        int[] aux = new int[work.length]; // Chi cap mot buffer cho ca cay
        Counters counters = new Counters();

        splitAndMerge(work, aux, 0, work.length, counters);
        return new Report(
                work,
                counters.inversions,
                counters.merges,
                counters.skipped);
    }

    // Su dung doan nua mo [lo, hi).
    private static void splitAndMerge(
            int[] a, int[] aux, int lo, int hi, Counters stats) {
        if (hi - lo <= 1) {
            return;
        }

        int mid = lo + (hi - lo) / 2;
        splitAndMerge(a, aux, lo, mid, stats);
        splitAndMerge(a, aux, mid, hi, stats);

        // Hai nua deu da sap: bien tiep giap du de xet ghep.
        if (a[mid - 1] <= a[mid]) {
            stats.skipped++;
            return;  // Khong co nghich the cheo.
        }

        stats.merges++;
        System.arraycopy(a, lo, aux, lo, hi - lo);

        int i = lo;
        int j = mid;

        for (int k = lo; k < hi; k++) {
            if (i >= mid) {
                a[k] = aux[j++];
            } else if (j >= hi) {
                a[k] = aux[i++];
            } else if (aux[i] <= aux[j]) {
                a[k] = aux[i++];  // Uu tien nua trai khi bang
            } else {
                a[k] = aux[j++];
                stats.inversions += mid - i;
            }
        }
    }

    private static void show(String label, int[] input) {
        Report report = analyze(input);
        System.out.println(
                label + ": " + Arrays.toString(report.sorted())
                + " | inversions=" + report.inversions()
                + ", merges=" + report.merges()
                + ", skipped=" + report.skipped());
    }

    public static void main(String[] args) {
        int[] original = {8, 4, 2, 1, 3, 1};

        show("Sample", original);
        show("Sorted", new int[]{1, 2, 3, 4, 5, 6});
        show("Reverse", new int[]{5, 4, 3, 2, 1});
        show("Duplicates", new int[]{2, 2, 1, 1});
        show("Extremes",
                new int[]{Integer.MAX_VALUE, Integer.MIN_VALUE, 0});
        show("Empty", new int[]{});
        show("Single", new int[]{42});

        System.out.println(
                "Input unchanged: " + Arrays.toString(original));
    }
}
```

Biên dịch, chạy với JDK 17 trở lên:

```bash
javac MergeWorkspaceReuse.java
java MergeWorkspaceReuse
```

**Stdout chính xác:**

```text
Sample: [1, 1, 2, 3, 4, 8] | inversions=12, merges=4, skipped=1
Sorted: [1, 2, 3, 4, 5, 6] | inversions=0, merges=0, skipped=5
Reverse: [1, 2, 3, 4, 5] | inversions=10, merges=4, skipped=0
Duplicates: [1, 1, 2, 2] | inversions=4, merges=1, skipped=2
Extremes: [-2147483648, 0, 2147483647] | inversions=2, merges=1, skipped=1
Empty: [] | inversions=0, merges=0, skipped=0
Single: [42] | inversions=0, merges=0, skipped=0
Input unchanged: [8, 4, 2, 1, 3, 1]
```

### Đọc kết quả thực nghiệm

- **Sample:** Có 12 cặp nghịch thế. Chương trình chỉ thực hiện 4 lượt merge và bỏ 1 lượt ghép khi hai nửa vốn đã ở đúng thứ tự.
- **Sorted:** Có 6 phần tử; cây chia đôi có 5 nút trong, cả 5 lượt merge đều được bỏ. Số nghịch thế 0, dữ liệu được sao chép một lần nhưng không bị trộn lại.
- **Reverse:** Mảng ngược thứ tự dài 5 có tối đa `5×4/2=10` nghịch thế. Cả 4 nút kết hợp đều phải merge.
- **Duplicates:** Với `[2,2,1,1]`, có 4 nghịch thế chéo giữa hai số 2 và hai số 1. Hai nửa riêng đã sắp nên bỏ hai lượt trộn con, chỉ trộn ở nút gốc.
- **Extremes:** Code so sánh `aux[i] <= aux[j]` trực tiếp, không trừ hai số có thể tràn kiểu int; số nghịch thế là 2.
- **Empty/Single:** Không có lời gọi merge nào vì đoạn dài ≤1; không có nghịch thế.
- **Input unchanged:** Mảng gốc còn đúng thứ tự ban đầu nhờ `clone()`.

**Tính chất cấp phát:** Mỗi lần gọi `analyze` tạo **một bản sao đầu vào và một aux cùng độ dài n** (ngoài đối tượng Report/Counters), nhưng **không tạo mảng con mới trong mỗi lời gọi splitAndMerge**. Việc có nhiều lần gọi `analyze` riêng biệt ở chương trình demo sẽ tạo buffer mới cho **mỗi lần chạy riêng**, không phải một buffer toàn cục. Điều này làm API dễ kiểm soát, tránh việc hai thao tác độc lập chia sẻ buffer mà không có quy tắc đồng bộ.

## 10. Các cách giảm chi phí kết hợp khác

### 10.1. Gộp nhiều thống kê vào một lượt

Trong lúc trộn hai đoạn đã sắp, có thể tính thêm những thống kê sử dụng trực tiếp thứ tự hai nửa, miễn là **chứng minh được công thức cập nhật**. Đếm nghịch thế là ví dụ điển hình. Tương tự, trong nhiều bài chia để trị, phần kết hợp có thể tích lũy số cặp thỏa điều kiện theo hai con trỏ hoặc kỹ thuật quét tuyến tính thay vì thêm vòng lặp duyệt lại mọi cặp.

Không phải thống kê nào cũng gộp miễn phí. Nếu thống kê phải duy trì một cấu trúc tốn O(log n) cho mỗi phần tử, chi phí combine có thể tăng theo. Cần đo lại C(n) chứ không chỉ viết “tính trong khi merge”.

### 10.2. Truyền chỉ số thay vì tạo mảng con

Thay vì:

```java
int[] left = Arrays.copyOfRange(a, 0, mid);
int[] right = Arrays.copyOfRange(a, mid, a.length);
```

hãy truyền **tham chiếu tới mảng gốc và các biên** `(lo, mid, hi)`. Cách này tránh cấp phát/copy để chia dữ liệu. Với Java, mảng không tự tạo view chỉ bằng slicing; gọi `Arrays.copyOfRange` thực sự tạo bản sao.

Nếu làm việc với cấu trúc khác (ví dụ `List.subList`), phải hiểu đặc tả view, thay đổi lan truyền và chi phí truy cập. Đừng mặc định mọi view có chi phí O(1) ở mọi kiểu danh sách hoặc đều an toàn với sửa đổi đồng thời.

### 10.3. Luân phiên hai buffer (*ping-pong merge sort*)

Một biến thể có thể **đổi vai trò mảng đọc và mảng ghi** theo từng mức đệ quy, nhờ đó tránh một số lượt chép `a→aux` ngay trước merge. Nguyên tắc cần giữ: tại mỗi lời gọi, phải biết chính xác **mảng nào chứa hai đoạn đã sắp**, và **mảng nào nhận output**; ở cơ sở đệ quy cũng phải bảo đảm phần tử được đặt đúng nơi.

Cách này có thể giảm băng thông sao chép trong một số triển khai nhưng làm bất biến và code phức tạp hơn. Không được đơn giản xóa `System.arraycopy` trong thuật toán đã viết mà vẫn đọc aux: khi ấy aux có thể chứa dữ liệu cũ hoặc chưa được khởi tạo, kết quả sẽ sai.

### 10.4. Đổi sang thuật toán đơn giản cho đoạn nhỏ

Khi độ dài đoạn còn nhỏ, `insertion sort` có overhead thấp và có thể tận dụng dãy gần có thứ tự. Một phương án là dừng chia khi độ dài ≤ngưỡng hằng (ví dụ 16–32 phần tử) và sắp đoạn bằng insertion sort, sau đó vẫn merge ở mức cha.

Với ngưỡng cố định, cận tiệm cận tổng thể thường vẫn O(n log n) ở trường hợp tổng quát, nhưng có thể giảm lời gọi hàm và thao tác quản lý buffer. Ngưỡng thực tế cần benchmark trên JVM và dữ liệu thật; không có một con số tốt nhất cho mọi hệ thống.

### 10.5. Đổi từ đệ quy sang bottom-up

**Bottom-up merge sort** khởi đầu từ các đoạn dài 1, ghép thành đoạn dài 2, rồi 4, 8... cho tới toàn dãy. Nó có thể dùng **một buffer chung**, tránh stack đệ quy nhưng cần cẩn thận ở đoạn cuối không đủ chiều dài. Chi phí thời gian tổng quát vẫn O(n log n), bộ nhớ phụ cho merge thường O(n).

Nếu cần sắp song song, các đoạn được merge cùng một lượt phải có **vùng ghi không chồng lấn**. Tái sử dụng cùng một aux vẫn có thể hợp lệ nếu phân chia quyền sở hữu theo đoạn; không được cho hai task ghi cùng chỉ số.

### 10.6. Trộn tại chỗ: đánh đổi không gian và độ phức tạp

Có thuật toán **in-place merge** cố gắng trộn bằng rất ít bộ nhớ ngoài mảng, nhưng các biến thể đơn giản có thể tốn nhiều lần dời phần tử. Ví dụ mỗi lần chèn một phần tử của nửa phải vào vị trí của nửa trái bằng cách dịch các phần tử trung gian có thể làm **O(m²)** công việc trên một đoạn m.

Do đó tối ưu “không cấp phát aux” không tự động tốt hơn: giảm bộ nhớ nhưng có thể **tăng thời gian** hoặc làm chứng minh/tính ổn định phức tạp hơn. Khi không có ràng buộc bộ nhớ gắt, một buffer O(n) với merge tuyến tính thường là lựa chọn đáng tin cậy.

## 11. Những lỗi thường gặp

1. **Cấp phát mảng phụ ngay trong mọi lời gọi merge.** Chạy đúng nhưng tạo nhiều đối tượng/ngốn công copy; nên cân nhắc tạo buffer chung ngoài cây.
2. **Tự nhận buffer reuse làm giảm Big O thời gian.** Reuse giảm allocation overhead; merge sort vẫn O(n log n) ở trường hợp tổng quát nếu tất cả mức đều phải merge.
3. **Nhầm dung lượng đỉnh với tổng lượng cấp phát.** Các mảng tạm tạo nối tiếp không đồng nghĩa tất cả còn sống cùng lúc; cần phân biệt khái niệm khi đo bộ nhớ.
4. **Quên sao chép dữ liệu trước khi merge bằng aux.** Nếu aux chưa chứa đúng hai nửa đã sắp, đọc từ aux cho kết quả sai.
5. **Dùng hai lời gọi song song ghi cùng vùng aux.** Buffer chung chỉ an toàn khi các đoạn ghi không chồng và có đồng bộ/ownership hợp lệ.
6. **Kiểm tra biên skip merge trước khi sắp hai nửa.** Hai giá trị biên chưa đủ chứng minh toàn đoạn có thứ tự nếu các nửa chưa sắp.
7. **Dùng điều kiện skip sai:** Đối với thứ tự tăng, `a[mid-1] <= a[mid]` là điều kiện đúng khi hai nửa đã tăng; đảo dấu sẽ làm bỏ merge không hợp lệ.
8. **Quên xử lý khi i hoặc j đã cạn.** Trong vòng merge phải ưu tiên lấy từ nửa còn phần tử; nếu truy cập `aux[i]` khi i==mid hoặc aux[j] khi j==hi sẽ vượt phạm vi.
9. **Làm mất tính ổn định ở trường hợp bằng nhau.** Khi khóa bằng, chọn nửa trái trước để giữ thứ tự trong một stable merge.
10. **Đếm nghịch thế bằng điều kiện `>=`.** Nghịch thế yêu cầu `a[i] > a[j]` nghiêm ngặt; hai giá trị bằng nhau **không** là nghịch thế.
11. **Cộng 1 thay vì cộng `mid-i` khi lấy phần tử từ nửa phải nhỏ hơn.** Một phần tử phải có thể tạo nghịch thế với **nhiều** phần tử trái còn lại.
12. **Dùng `int` cho số nghịch thế.** Tổng có thể lên tới n(n−1)/2; dùng `long`.
13. **Sao chép cả mảng trong mọi lượt merge.** Chỉ cần copy đoạn đang trộn `[lo,hi)`; copy toàn n tại mỗi nút có thể tăng khối lượng sao chép rất nhiều.
14. **Nhầm đoạn đóng và nửa mở.** Mã dùng `[lo,hi)`, điểm giữa mid thuộc nửa phải và độ dài đoạn là hi−lo.
15. **Nghĩ bỏ merge đồng nghĩa bỏ luôn việc đệ quy.** Cần sắp xong hai nửa trước để biết có thể ghép không cần trộn; mảng đã sắp vẫn đi qua các lời gọi chia.
16. **Bỏ qua chi phí của clone khi công bố bộ nhớ.** Mã giữ nguyên input nên tồn tại cả bản sao và aux; vẫn O(n), nhưng không phải “chỉ cấp đúng một mảng”.
17. **Không xác định luồng dữ liệu trong ping-pong buffer.** Đổi vai trò đọc/ghi sai có thể ghi đè dữ liệu chưa đọc hoặc trả kết quả ở nhầm mảng.

## 12. Bài tập tự kiểm tra có đáp án

**Bài 1.** Merge sort có hệ thức `T(n)=2T(n/2)+Θ(n)`. Nếu một phương án combine dùng hai vòng lặp lồng nhau làm `C(n)=Θ(n²)`, độ phức tạp tổng trở thành gì?

**Đáp án:** Với các nửa cân bằng, `T(n)=2T(n/2)+Θ(n²)=Θ(n²)`. Chi phí combine tại mức gốc đã là Θ(n²) và tổng các mức nhỏ hơn tạo cùng cấp.

**Bài 2.** Vì sao tạo một mảng aux dài n ngoài cây đệ quy không tự làm merge sort thành O(n) thời gian?

**Đáp án:** Các phần tử vẫn có thể phải được đọc/ghi trong lượt merge ở **mỗi** mức log n, tạo tổng O(n log n). Một aux giúp tránh cấp phát mảng mới, nhưng không loại bỏ các lượt merge cần thiết.

**Bài 3.** Hai nửa đã sắp là `[1,3,5]` và `[5,6,9]`. Có thể bỏ merge không? Điều này có giữ tính ổn định không?

**Đáp án:** Có, vì 5≤5 tại biên. Ghép hai nửa đã tạo đoạn tăng không giảm; các phần tử bằng 5 của nửa trái vẫn ở trước nửa phải, nên giữ ổn định.

**Bài 4.** Với hai nửa đã sắp `[2,5,8]` và `[3,7]`, có bao nhiêu nghịch thế chéo?

**Đáp án:** Có **3**: (5,3), (8,3), (8,7). Khi chọn 3 từ nửa phải, cộng 2; khi chọn 7 từ nửa phải, cộng 1.

**Bài 5.** Mảng `[2,2,1,1]` có bao nhiêu nghịch thế? Hai giá trị 2 có tạo nghịch thế với nhau không?

**Đáp án:** Có **4** nghịch thế vì mỗi số 2 đứng trước cả hai số 1. Hai số 2 bằng nhau không tạo nghịch thế do định nghĩa cần dấu lớn hơn nghiêm ngặt.

**Bài 6.** Với n=6 đã sắp tăng, cây merge sort chia đến đoạn một phần tử có bao nhiêu nút kết hợp? Tối ưu skip merge sẽ gọi combine thực sự bao nhiêu lần?

**Đáp án:** Có **5 nút kết hợp** trong cây nhị phân đầy đủ có 6 lá. Vì tất cả biên đều đúng thứ tự, số merge thực sự bằng **0**, số lượt bỏ qua bằng **5**.

**Bài 7.** Tại sao mảng `aux` dùng chung an toàn trong merge sort tuần tự dù cả nút cha và hai nút con đều dùng cùng vùng chỉ số?

**Đáp án:** Hai nút con đã kết thúc trước khi cha bắt đầu merge. Cha có thể sao chép lại dữ liệu mới nhất vào aux rồi đọc từ đó; không có hai thao tác merge cùng lúc ghi đè vùng đang dùng. Với tính song song, cần thêm quy tắc phân đoạn/ownership.

**Bài 8.** Nếu muốn API sắp xếp mà **không thay đổi mảng đầu vào**, trong mã minh họa cần các vùng nhớ nào và tổng cấp độ bộ nhớ là gì?

**Đáp án:** Một bản sao `work` dài n, một `aux` dài n, stack đệ quy O(log n) và bộ đếm/Report O(1). Tổng không gian phụ O(n).

**Bài 9.** Vì sao tính tổng nghịch thế bằng `long` thay vì `int`?

**Đáp án:** Dãy ngược thứ tự có n(n−1)/2 nghịch thế, có thể vượt 2.147.483.647 khi n đủ lớn. `long` có miền lớn hơn và đủ chứa số cặp của một mảng Java `int[]` có độ dài hợp lệ.

**Bài 10.** Có nên bỏ ngay `System.arraycopy` để “tiết kiệm một pass” mà giữ nguyên các phép đọc `aux[i]` và `aux[j]`?

**Đáp án:** Không. Cách merge được viết đòi aux chứa **bản sao mới nhất của đoạn [lo,hi)**. Xóa copy mà không thiết kế lại vai trò nguồn/đích làm đọc dữ liệu cũ hoặc chưa khởi tạo. Muốn tránh copy phải dùng thiết kế khác có bất biến rõ ràng, ví dụ ping-pong buffer.

## Ghi nhớ

Để tối ưu một thuật toán **chia để trị**, hãy phân tích **C(n) ở bước kết hợp** trước khi thay đổi code. Với merge sort, hai con trỏ giúp trộn mỗi đoạn dài m trong Θ(m). Một **mảng aux cấp phát một lần và được truyền cùng biên đoạn** giảm cấp phát/copy dư thừa; điều kiện `a[mid−1] <= a[mid]` cho phép **bỏ merge** khi hai nửa đã có thứ tự; việc **đếm nghịch thế ngay trong merge** tránh một lượt kiểm tra cặp O(n²). Phân biệt rõ **thời gian tiệm cận, số lần cấp phát, bộ nhớ đỉnh và số lượt di chuyển phần tử**. Tái sử dụng workspace chỉ an toàn khi xác định đúng phạm vi, vòng đời và quyền ghi, đặc biệt khi có đệ quy hoặc chạy song song.
