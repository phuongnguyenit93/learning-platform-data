# Tách dữ liệu tĩnh khỏi dữ liệu thay đổi

**Tách dữ liệu tĩnh khỏi dữ liệu thay đổi** là kỹ thuật thiết kế thuật toán nhằm nhận diện phần dữ liệu giữ nguyên trong một giai đoạn, tiền xử lý nó một lần và quản lý các thay đổi bằng trạng thái riêng. Khi truy vấn, ta có thể dùng kết quả tiền xử lý của phần tĩnh rồi kết hợp ảnh hưởng của phần động, **nếu phép toán cho phép**. Tư tưởng này đặc biệt quan trọng trong bài toán biến đổi, tiền xử lý và xử lý nhiều truy vấn xen kẽ cập nhật.

Một hệ thống có thể gồm **snapshot cơ sở** (ảnh chụp dữ liệu tại một thời điểm), **delta** (những thay đổi kể từ snapshot), và **chỉ mục dẫn xuất** (tổng tiền tố, tần suất, cấu trúc tìm kiếm...). Điều cần đảm bảo không phải chỉ là lưu các phần đó ở các biến khác nhau: phải có **bất biến liên kết** giữa dữ liệu hiện tại với snapshot, delta và kết quả truy vấn.

**Mục tiêu:** phân biệt phần nào thực sự bất biến, phần nào có thể cập nhật; xây mô hình base + delta; tính chi phí tiền xử lý, cập nhật và truy vấn; chọn tái xây hay cấu trúc động; tránh stale cache và đếm trùng cập nhật; triển khai Java 17+ với tổng tiền tố tĩnh kết hợp Fenwick tree lưu delta; biết khi nào không thể áp dụng phép hiệu chỉnh đơn giản.

## 1. Động cơ: khi tiền xử lý gặp cập nhật

Cho mảng `a=[5,-2,7,1,-3,4]` có n=6 phần tử. Nếu mảng **không thay đổi**, ta có thể xây tổng tiền tố:

`prefix=[0,5,3,10,11,8,12]`.

Tổng đoạn nửa mở `[1,5)` là:

`prefix[5]-prefix[1] = 8-5 = 3`,

tương ứng `(-2)+7+1+(-3)=3`.

Sau khi cập nhật `a[2]` từ 7 thành 10, tổng đoạn đó trở thành **6**, nhưng mảng tiền tố cũ **vẫn cho kết quả 3**. Đây không phải lỗi trong công thức tổng tiền tố; lỗi là **dùng dữ liệu dẫn xuất của phiên bản cũ cho phiên bản mới**.

Có nhiều hướng giải quyết:

1. **Không tiền xử lý:** giữ mảng hiện tại, cập nhật O(1), mỗi truy vấn cộng từng phần tử O(n) trong trường hợp xấu.
2. **Xây lại sau cập nhật:** cập nhật mảng, tái tính tiền tố O(n), truy vấn O(1) cho đến lần thay đổi tiếp theo.
3. **Dùng cấu trúc động:** Fenwick tree hoặc segment tree hỗ trợ cập nhật điểm và tổng đoạn với O(log n) mỗi thao tác.
4. **Tách cơ sở khỏi thay đổi:** giữ `basePrefix` đúng với snapshot ban đầu, biểu diễn thay đổi bằng `delta`; trả lời bằng tổng cơ sở cộng tổng hiệu chỉnh. Delta có thể lưu trong Fenwick hoặc nhật ký sự kiện.

Không hướng nào luôn tốt nhất; **n, số cập nhật u, số truy vấn q, bộ nhớ và loại phép toán** quyết định lựa chọn.

## 2. Hiểu đúng dữ liệu tĩnh, động và dẫn xuất

“Tĩnh” và “động” mô tả hợp đồng thao tác trong một giai đoạn, không phải đặc tính vĩnh viễn của biến.

- **Tĩnh:** dữ liệu được đảm bảo không đổi trong giai đoạn sử dụng. Ví dụ tập chỉ số mảng, snapshot bản ghi, từ điển khóa đã biết trước.
- **Động:** dữ liệu được phép thay đổi bởi các thao tác hợp lệ, như thay một giá trị, tăng bộ đếm, thêm một sự kiện.
- **Dẫn xuất:** dữ liệu tính từ nguồn, như prefix sum, thứ tự đã sắp xếp, bảng đếm, chỉ số tìm kiếm hoặc một kết quả cache. Dữ liệu dẫn xuất có thể lỗi thời khi đầu vào liên quan thay đổi.
- **Bất biến:** mệnh đề vẫn đúng sau mọi cập nhật được phép, làm cơ sở chứng minh truy vấn chính xác.

Ví dụ danh mục sản phẩm có **mã danh mục** cố định nhưng **số lượng hàng** biến động. Mã là phần tĩnh, số lượng là phần động. Nếu thêm mã danh mục mới, từ điển mã **không còn tĩnh** theo hợp đồng cũ, và hệ thống cần một cách mở rộng hoặc tái tiền xử lý.

Một đồ thị cũng có thể giữ **đỉnh và cạnh** không đổi, nhưng **trọng số** thay đổi. Danh sách kề có thể dùng lại, song kết quả đường đi ngắn nhất tính theo trọng số cũ có thể không còn đúng. **Tách dữ liệu đầu vào không đồng nghĩa mọi kết quả dẫn xuất đều tái sử dụng được.**

### Phân loại theo thao tác

| Hợp đồng thao tác | Cách làm thường phù hợp | Điều kiện quan trọng |
|---|---|---|
| Nhiều truy vấn, không thay đổi dữ liệu | Prefix sum, bảng tần suất tĩnh, tìm kiếm trên dãy đã sắp | Bảng tiền xử lý đúng cho tất cả truy vấn |
| Thay một phần tử và hỏi tổng đoạn xen kẽ | Fenwick / segment tree | Cấu trúc được cập nhật sau mỗi lần thay đổi |
| Vài đợt cập nhật, nhiều truy vấn giữa các đợt | Tái xây bảng tiền xử lý theo đợt | Không đọc bảng cũ khi đã có thay đổi chưa gộp |
| Thêm giá trị lên nhiều đoạn, cuối cùng mới cần mảng | Mảng hiệu, quét cộng dồn cuối cùng | Truy vấn không cần xen kẽ với cập nhật |
| Nền ít đổi, số bản ghi cập nhật nhỏ | Snapshot + delta | Tính đúng phép gộp và tránh đếm trùng |
| Thay đổi tập khóa hoặc thứ tự liên tục | Chỉ mục hoặc cấu trúc tìm kiếm động | Không dựa vào ánh xạ/sắp xếp đã lỗi thời |

Trước khi chọn cách tách, phải trả lời: **truy vấn hỏi tổng, min/max, tìm kiếm, đếm hay một phép toán khác?** Cùng một mô hình snapshot + delta có thể rất thuận tiện cho **tổng**, nhưng không đủ cho **min** hoặc **vị trí theo thứ tự**.

## 3. Mô hình toán học base + delta

Giả sử mảng `base[0..n-1]` là snapshot không đổi. Mảng `current` chứa trạng thái hiện tại. Định nghĩa:

**`delta[i] = current[i] - base[i]`.**

Bất biến phải giữ sau mọi thao tác:

**`current[i] = base[i] + delta[i]`**, với mọi vị trí hợp lệ i.

Ban đầu `current=base` và tất cả `delta[i]=0`. Khi một vị trí i thay từ `old` sang `new`, hãy cộng vào delta một lượng:

**`change = new - old`**.

Sau đó `current[i]=new`. Vì:

`old = base[i]+delta[i]`,

nên:

`new = base[i]+delta[i]+change`.

Do đó bất biến vẫn đúng. Cần tính change từ **giá trị hiện tại ngay trước cập nhật**, chứ không phải luôn từ snapshot.

### Cập nhật lặp một vị trí

Giả sử `base[2]=7`.

| Thao tác | Giá trị current[2] | change của thao tác | delta ròng |
|---|---:|---:|---:|
| Ban đầu | 7 | — | 0 |
| `set(2,10)` | 10 | +3 | +3 |
| `set(2,6)` | 6 | -4 | -1 |
| `set(2,7)` | 7 | +1 | 0 |

Nếu thay vì lưu các gia số, ta dùng mảng delta cho từng chỉ số và **gán lại toàn bộ** `delta[i]`, thì có thể đặt `delta[i]=new-base[i]`. Hai cách biểu diễn đều hợp lệ **nếu không trộn lẫn quy tắc**. Đặt `delta[i]+=new-base[i]` sau mỗi sự kiện sẽ sai khi cùng chỉ số bị sửa nhiều lần.

### Tách tổng một đoạn

Với đoạn nửa mở `[l,r)`, `0≤l≤r≤n`:

`sumCurrent(l,r) = Σ(current[i]) = Σ(base[i]+delta[i])`,

nên:

**`sumCurrent(l,r) = sumBase(l,r) + sumDelta(l,r)`.**

Xây `basePrefix[0]=0`, `basePrefix[k+1]=basePrefix[k]+base[k]`. Khi đó:

**`sumCurrent(l,r) = (basePrefix[r]-basePrefix[l]) + sumDelta(l,r)`.**

Phần tĩnh được tính trong **O(1)** sau tiền xử lý. Phần `sumDelta` có thể tính từ nhật ký thay đổi ngắn hoặc một cấu trúc hỗ trợ tổng động.

Đây là sự tách hợp lệ vì **phép cộng có tính kết hợp** và tổng các hiệu chỉnh tương ứng chính xác với hiệu của hai dãy. Không thể tùy tiện thay tổng bằng mọi hàm truy vấn khác.

## 4. Chỉ số và kiểu dữ liệu phải thống nhất

Trong bài này dùng chỉ số Java 0-based và đoạn **nửa mở `[l,r)`**:

- Độ dài đoạn là `r-l`.
- Đoạn rỗng `[i,i)` có tổng 0.
- Toàn bộ mảng là `[0,n)`.
- Đoạn đóng 0-based `[l,r]` tương đương `[l,r+1)`.
- Đoạn đóng 1-based `[L,R]` tương đương `[L-1,R)`.

Với prefix kích thước `n+1`, `prefix[r]-prefix[l]` cho đúng tổng đoạn `[l,r)`, kể cả khi l=0 hoặc l=r. Một lỗi thường gặp là trừ `prefix[l+1]` hoặc quên cộng 1 vào biên phải của đoạn đóng.

Về kiểu số, một phần tử có thể vừa `int` nhưng tổng nhiều phần tử có thể vượt `Integer.MAX_VALUE`. Dùng `long` cho tổng. Đặc biệt, nếu đổi từ `Integer.MIN_VALUE` sang `Integer.MAX_VALUE`, mức chênh là **4.294.967.295**, vượt int; phép trừ phải thực hiện trên kiểu long:

~~~java
// Mã minh họa: newValue và oldValue là int.
long change = (long) newValue - oldValue;
~~~

Ép kiểu **sau** phép trừ sẽ không sửa được kết quả đã tràn int.

## 5. Fenwick tree để lưu phần thay đổi

**Fenwick tree (Binary Indexed Tree)** hỗ trợ cộng một giá trị vào một vị trí và tính tổng tiền tố trong O(log(n+1)), dùng O(n) bộ nhớ. Với mô hình này, Fenwick không lưu trực tiếp các giá trị current mà lưu **tổng của các delta**.

Trên chỉ số 1-based của Fenwick, `bit[p]` chứa tổng một nhóm phần tử có độ dài `lowbit(p)=p & (-p)`, kết thúc tại p.

### Cập nhật một vị trí

Để cộng `change` vào `delta[index]` (với index 0-based):

~~~java
// Mảnh mã minh họa trong một lớp có long[] bit.
for (long p = index + 1L; p < bit.length; p += p & -p) {
    bit[(int) p] += change;
}
~~~

Từ vị trí index+1, các bước `p += lowbit(p)` lần lượt ghé qua những nhóm chứa vị trí đã sửa. Mỗi nhóm nhận đúng một lần hiệu chỉnh. Dùng biến p là long để phép tăng chỉ số không tràn int khi kích thước lớn. Số bước O(log(n+1)).

### Truy vấn tổng tiền tố delta

~~~java
// Mảnh mã minh họa, endExclusive nằm trong [0,n].
long total = 0;
for (int p = endExclusive; p > 0; p -= p & -p) {
    total += bit[p];
}
~~~

Mỗi nhóm Fenwick được cộng đúng một lần, các nhóm không chồng nhau và ghép thành tiền tố `[0,endExclusive)`. Do đó:

`sumDelta(l,r)=deltaPrefix(r)-deltaPrefix(l)`.

Hai đoạn mã trên là **các mảnh minh họa**, chưa phải lớp Java độc lập. Chương trình runnable ở phần 9.

### Vì sao không dùng Fenwick trực tiếp trên current?

Hoàn toàn có thể. Nếu chỉ cần **cập nhật điểm + truy vấn tổng đoạn**, Fenwick trên giá trị hiện tại đã đủ, thường gọn hơn mô hình lai. Lưu `basePrefix + Fenwick(delta)` **không cải thiện độ phức tạp tiệm cận**: cập nhật và truy vấn vẫn O(log n), bộ nhớ vẫn O(n), thậm chí có thêm mảng snapshot.

Giá trị của mô hình lai là **tách vai trò**: có kết quả tĩnh được chia sẻ, nhìn thấy ảnh hưởng riêng của cập nhật, quản lý các phiên bản và tái xây snapshot tại mốc thích hợp. Không được tuyên bố mô hình lai luôn nhanh hơn Fenwick thường.

## 6. Tái xây (rebase) và tính nhất quán

Sau nhiều cập nhật, snapshot cũ vẫn đúng đối với **phiên bản gốc**, không đúng đối với current nếu dùng một mình. Có thể chọn một thời điểm để **tái xây**:

1. Lấy `newBase=current.clone()`.
2. Xây lại `newBasePrefix` từ newBase.
3. Đặt Fenwick delta về toàn số 0.
4. Tiếp tục nhận cập nhật mới so với snapshot mới.

Trước khi rebase, `current=oldBase+oldDelta`. Sau rebase, `newBase=current` và `newDelta=0`. Mọi tổng đoạn của current **không được đổi** chỉ vì thao tác tái xây.

**Bẫy đếm trùng:** nếu snapshot mới đã chứa các cập nhật cũ mà vẫn cộng lại delta cũ, kết quả lớn hơn thực tế. **Bẫy bỏ sót:** nếu xóa delta trước nhưng truy vấn vẫn sử dụng snapshot cũ, kết quả mất phần thay đổi. Vì thế bộ snapshot và delta phải thuộc **cùng một phiên bản logic**.

Trong chương trình **một luồng**, có thể thay lần lượt các trường rồi chỉ phục vụ truy vấn khi thao tác rebase hoàn tất. Trong ứng dụng đa luồng, thay nhiều trường độc lập **không tự động là một giao dịch nguyên tử**. Cần khóa, xuất bản một snapshot bất biến kèm delta phù hợp hoặc cơ chế đồng bộ/versioning. Mã Java bên dưới được định nghĩa cho **một luồng**, không tuyên bố thread-safe.

**Rebase không bắt buộc theo số lần cập nhật khi dùng Fenwick:** cây Fenwick vẫn cho truy vấn O(log n) bất kể đã xử lý bao nhiêu sự kiện. Tái xây có thể phục vụ yêu cầu snapshot mới hoặc nghiệp vụ. Với **nhật ký thay đổi chưa gộp**, ngược lại, số bản ghi log chưa xử lý có thể làm mỗi truy vấn ngày càng chậm, nên cần gộp hoặc tái xây định kỳ.

## 7. Tính chi phí của các phương án

Gọi n là độ dài mảng, u là số cập nhật điểm, q là số truy vấn tổng đoạn. Giả sử mỗi phép số học trên long có chi phí O(1).

| Phương án | Khởi tạo/tiền xử lý | Cập nhật | Truy vấn tổng đoạn | Bộ nhớ phụ |
|---|---:|---:|---:|---:|
| Quét current trực tiếp | O(1) ngoài lưu mảng | O(1) | O(n) xấu nhất | O(1) |
| Prefix, xây lại sau **mỗi** cập nhật | O(n) | O(n) | O(1) | O(n) |
| Fenwick trên current | O(n) nếu xây tuyến tính | O(log(n+1)) | O(log(n+1)) | O(n) |
| Segment tree tổng | O(n) | O(log(n+1)) | O(log(n+1)) | O(n) |
| Prefix tĩnh + Fenwick(delta) | O(n) | O(log(n+1)) | O(log(n+1)) | O(n) |
| Prefix tĩnh + danh sách ≤B sự kiện chưa gộp | O(n) | O(1) ghi log, cộng chi phí tái xây | O(B) | O(n+B) |

Nếu mỗi B sự kiện ta tái xây prefix trong O(n), và chỉ tái xây sau những nhóm B cập nhật **đầy đủ**, tổng độ phức tạp của hướng cuối là:

**`O(n + u + ⌊u/B⌋·n + qB)`**.

Mỗi truy vấn tính `sumBase` trong O(1), rồi duyệt nhiều nhất B sự kiện chưa gộp, cộng những `change` có chỉ số thuộc đoạn. Khi một chỉ số được cập nhật lặp lại, log cần lưu **gia số giữa hai trạng thái liên tiếp**, không được cộng những giá trị `new-base` nhiều lần. Đây là mô hình chi phí; để triển khai thực tế còn cần cách lưu log, kiểm tra chỉ số và xử lý phiên bản.

### Khi nào tái xây thường hợp lý?

- Nếu u=0 và q lớn, **prefix thuần** cho O(n+q), không cần cơ chế cập nhật.
- Nếu u rất ít và q rất nhiều giữa các lần sửa, **tái xây theo đợt** có thể đơn giản và hiệu quả.
- Nếu u và q xen kẽ liên tục, **Fenwick hoặc segment tree** giúp tránh O(n) sau mỗi cập nhật.
- Nếu q rất nhỏ còn u lớn, cập nhật trực tiếp rồi quét lúc cần có thể rẻ hơn việc duy trì nhiều cấu trúc.
- Nếu cần xử lý min/max, gán đoạn hoặc phép gộp phức tạp, nên xét **segment tree** hay cấu trúc khác theo đúng loại thao tác.

Không nên chọn chỉ vì thấy O(log n) nhỏ hơn O(n): phải cộng cả tiền xử lý, bộ nhớ, tần suất cập nhật, truy vấn và hệ số thực tế.

## 8. Hai cách lưu delta: giá trị ròng và sự kiện

### 8.1. Delta ròng theo vị trí

Có thể lưu `delta[i]` cho từng vị trí, hoặc dùng `Map<index,delta>` nếu rất ít vị trí khác base. Khi thay một giá trị bằng new, **gán**:

`delta[i]=new-base[i]`.

Nếu dùng Fenwick vốn hỗ trợ **cộng gia số**, hãy gọi cập nhật với `change=new-current[i]`. Khi dùng một map thưa, các chỉ số đã trở lại giá trị base có delta bằng 0 có thể được xóa khỏi map.

Sự khác biệt giữa **số vị trí có delta khác 0** và **số sự kiện cập nhật** rất quan trọng. Có thể có một nghìn sự kiện sửa cùng một chỉ số nhưng cuối cùng delta ròng bằng 0.

### 8.2. Nhật ký thay đổi

Nếu cần kiểm toán, có thể lưu các sự kiện `(index,change,time)`. Các sự kiện thay giá trị 7→10→6→7 lần lượt có change `+3,-4,+1`, tổng bằng 0. Khi truy vấn ảnh chụp theo phiên bản, chỉ áp dụng những sự kiện **sau phiên bản snapshot đang dùng** và **trước hoặc tại phiên bản được hỏi**.

Không được lấy snapshot đã chứa U1 rồi áp dụng U1 lần nữa. Nếu một nhật ký vừa dùng cho kiểm toán vừa dùng làm delta hoạt động, cần đánh dấu ranh giới giữa phần **đã gộp** và phần **chưa gộp**.

### 8.3. Khi nào phép cộng hiệu chỉnh không hợp lệ?

Đối với tổng, `sum(base+delta)=sum(base)+sum(delta)`. Nhưng không phải mọi phép truy vấn đều phân tách tương tự.

Phản ví dụ:

`base=[1,100]`, `delta=[100,-100]`, do đó `current=[101,0]`.

`min(current)=0`, còn `min(base)+min(delta)=1-100=-99`. Vì vậy **min hiện tại không bằng min cơ sở cộng min delta**.

Tương tự, thay một giá trị trong mảng đã sắp xếp có thể phá thứ tự; không thể dùng binary search trên snapshot rồi tự suy ra kết quả hiện tại nếu không có cơ chế bổ sung. Cần kiểm tra phép toán, không chỉ hình thức dữ liệu.

## 9. Java 17+ hoàn chỉnh: prefix tĩnh + Fenwick delta

Chương trình bên dưới dùng **đoạn nửa mở `[l,r)`**, cập nhật bằng phép gán **`update(index,newValue)`** và cung cấp `rebase()`. Nó dùng `clone()` để tách đầu vào của người gọi khỏi trạng thái bên trong.

- `baseSnapshot`: snapshot hiện tại, không thay đổi bởi `update`.
- `current`: dữ liệu logic sau mọi cập nhật.
- `basePrefix`: tổng tiền tố của snapshot, không đổi giữa hai lần rebase.
- `deltaTree`: Fenwick lưu tổng những thay đổi **so với snapshot**.
- `staticPart` và `deltaPart`: hai thành phần của tổng đoạn.
- `sum`: tổng thật của current trên một đoạn.
- Với mảng rỗng, `sum(0,0)=0` và mọi `update` đều không hợp lệ.

Lưu tệp **`StaticDeltaRangeSumDemo.java`**:

~~~java
import java.util.Arrays;

public final class StaticDeltaRangeSumDemo {
    static final class Index {
        private int[] baseSnapshot;
        private final int[] current;
        private long[] basePrefix;
        private long[] deltaTree;

        Index(int[] initial) {
            if (initial == null) {
                throw new IllegalArgumentException("Null input");
            }
            current = initial.clone();
            rebase();
        }

        // Lấy current làm snapshot mới; không thay giá trị logic.
        void rebase() {
            baseSnapshot = current.clone();
            basePrefix = new long[baseSnapshot.length + 1];
            for (int i = 0; i < baseSnapshot.length; i++) {
                basePrefix[i + 1] = basePrefix[i] + baseSnapshot[i];
            }
            deltaTree = new long[baseSnapshot.length + 1];
        }

        // Gán giá trị mới ở một vị trí.
        void update(int index, int newValue) {
            if (index < 0 || index >= current.length) {
                throw new IndexOutOfBoundsException("Invalid index");
            }
            long change = (long) newValue - current[index];
            if (change == 0L) {
                return;
            }
            current[index] = newValue;

            // Fenwick tree 1-based, lưu phần delta.
            for (long p = index + 1L;
                    p <= current.length; p += p & -p) {
                deltaTree[(int) p] += change;
            }
        }

        private void checkRange(int left, int rightExclusive) {
            if (left < 0 || left > rightExclusive
                    || rightExclusive > current.length) {
                throw new IndexOutOfBoundsException("Invalid range");
            }
        }

        private long deltaPrefix(int endExclusive) {
            long total = 0;
            for (int p = endExclusive; p > 0; p -= p & -p) {
                total += deltaTree[p];
            }
            return total;
        }

        long staticPart(int left, int rightExclusive) {
            checkRange(left, rightExclusive);
            return basePrefix[rightExclusive] - basePrefix[left];
        }

        long deltaPart(int left, int rightExclusive) {
            checkRange(left, rightExclusive);
            return deltaPrefix(rightExclusive) - deltaPrefix(left);
        }

        long sum(int left, int rightExclusive) {
            checkRange(left, rightExclusive);
            long base = basePrefix[rightExclusive] - basePrefix[left];
            long delta = deltaPrefix(rightExclusive)
                    - deltaPrefix(left);
            return base + delta;
        }
    }

    public static void main(String[] args) {
        int[] initial = {5, -2, 7, 1, -3, 4};
        Index index = new Index(initial);

        System.out.println("Initial [1,5): " + index.sum(1, 5));

        index.update(2, 10); // 7 -> 10, delta +3
        index.update(4, 2);  // -3 -> 2, delta +5

        System.out.println("After updates [1,5): "
                + index.sum(1, 5));
        System.out.println("Static part [1,5): "
                + index.staticPart(1, 5));
        System.out.println("Delta part [1,5): "
                + index.deltaPart(1, 5));
        System.out.println("All [0,6): " + index.sum(0, 6));

        index.rebase();
        System.out.println("After rebuild [1,5): "
                + index.sum(1, 5));
        System.out.println("Delta after rebuild [1,5): "
                + index.deltaPart(1, 5));

        index.update(0, -1); // 5 -> -1, delta -6
        System.out.println("After update [0,3): "
                + index.sum(0, 3));
        System.out.println("All [0,6): " + index.sum(0, 6));
        System.out.println("Input unchanged: "
                + Arrays.toString(initial));
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac StaticDeltaRangeSumDemo.java
java StaticDeltaRangeSumDemo
~~~

**Đầu ra chính xác:**

~~~text
Initial [1,5): 3
After updates [1,5): 11
Static part [1,5): 3
Delta part [1,5): 8
All [0,6): 20
After rebuild [1,5): 11
Delta after rebuild [1,5): 0
After update [0,3): 7
All [0,6): 14
Input unchanged: [5, -2, 7, 1, -3, 4]
~~~

### Kiểm tra phép tính

Ban đầu đoạn `[1,5)` gồm `[-2,7,1,-3]`, tổng 3. Hai cập nhật làm giá trị tại index 2 tăng 3 và tại index 4 tăng 5, nên tổng đoạn lên **3+3+5=11**. Phần tĩnh vẫn 3, phần delta là 8; tổng toàn mảng ban đầu 12, sau cập nhật là **20**.

Rebase lấy `[5,-2,10,1,2,4]` làm snapshot mới, nên tổng `[1,5)` vẫn 11 nhưng delta của đoạn ấy trở về 0. Sau đó thay index 0 từ 5 thành -1, tổng toàn mảng giảm 6 xuống **14**; đoạn `[0,3)` gồm `[-1,-2,10]` có tổng **7**. Mảng đầu vào `initial` của người gọi vẫn giữ nguyên.

### Chứng minh bất biến của mã

**Khởi tạo:** current được sao chép từ initial; baseSnapshot sao chép từ current, basePrefix phản ánh đúng snapshot, Fenwick delta bằng 0. Do đó mọi truy vấn trả đúng tổng current.

**Cập nhật:** `change=new-old` được cộng vào Fenwick ở một chỉ số logic. Mọi tổng đoạn chứa chỉ số ấy tăng change, các đoạn khác giữ nguyên; current cũng được gán thành new. Quan hệ current=base+delta tiếp tục đúng.

**Rebase:** baseSnapshot sao chép current, prefix tính lại từ baseSnapshot và cây delta được đặt lại 0. Current không đổi; vì thế mọi truy vấn sau rebase trả cùng kết quả như ngay trước đó, nếu không có cập nhật mới xen vào.

**Truy vấn:** tổng cơ sở được tính từ hai giá trị basePrefix; tổng hiệu chỉnh từ hiệu hai tiền tố Fenwick. Theo đẳng thức tổng của base+delta, tổng trả về bằng tổng current của đúng đoạn yêu cầu.

### Phân tích độ phức tạp Java

- Khởi tạo và `rebase()`: **Θ(n)** thời gian, cấp phát O(n) bộ nhớ cho snapshot, prefix và Fenwick.
- `update`: **O(log(n+1))** thời gian; trường hợp gán giá trị bằng cũ là O(1).
- `sum` hoặc `deltaPart`: **O(log(n+1))** do hai truy vấn Fenwick, O(1) trạng thái tạm.
- `staticPart`: O(1) sau tiền xử lý.
- Tổng bộ nhớ lưu giữ: **Θ(n)** cho các mảng `baseSnapshot`, `current`, `basePrefix`, `deltaTree`.

Các phép tổng sử dụng kiểu long. Với phần tử int và chiều dài mảng Java thực tế, tổng của các phần tử current nằm trong miền long; nếu mở rộng sang các phần tử long không có cận tổng, phải phân tích tràn số hoặc sử dụng kiểu số phù hợp. Mã **không hỗ trợ sử dụng đồng thời từ nhiều luồng**.

## 10. Những ví dụ khác của tách tĩnh và động

### 10.1. Nén tọa độ

Nếu tập khóa có thể xuất hiện được **biết trước**, hãy sắp các khóa phân biệt rồi ánh xạ mỗi khóa sang chỉ số 0..k−1. Bảng ánh xạ là phần tĩnh; bộ đếm hoặc Fenwick theo các chỉ số nén là phần động.

**Offline:** biết trước toàn bộ khóa của cập nhật/truy vấn nên có thể nén một lần, kể cả khóa xuất hiện trong sự kiện tương lai.

**Online:** nếu một khóa chưa có trong bảng xuất hiện bất ngờ, chỉ mục nén tĩnh có thể không đủ. Thêm khóa giữa dãy đã sắp có thể làm dịch chỉ số và khiến các bảng dẫn xuất cũ sai. Cần cấu trúc động, bộ chỉ mục bổ sung hoặc tái nén có kiểm soát.

### 10.2. Dãy đã sắp xếp và tìm kiếm

Mảng `[1,3,5,7]` cho phép tìm nhị phân. Nếu thay phần tử thứ hai thành 9, mảng thành `[1,9,5,7]`, không còn sắp xếp. Sự thay đổi chỉ ở một vị trí, nhưng **bất biến dùng cho binary search đã bị phá**. Việc giữ một bản đã sắp của snapshot không tự đảm bảo truy vấn tìm kiếm trên current đúng.

Phải duy trì thứ tự lúc cập nhật, tái sắp xếp hoặc dùng cấu trúc tìm kiếm động. Đây là ví dụ cho thấy không thể áp dụng cùng phép hiệu chỉnh tổng đoạn cho mọi loại truy vấn.

### 10.3. Đồ thị có cấu trúc tĩnh

Tập đỉnh/cạnh không đổi có thể được lưu trong danh sách kề cố định, còn trọng số cạnh có thể được lưu riêng. Nhưng khi trọng số thay đổi, khoảng cách ngắn nhất tính trước đó có thể không còn đúng. Ta tái sử dụng **cấu trúc kết nối**, không mặc nhiên tái sử dụng **mọi kết quả thuật toán phụ thuộc trọng số**.

### 10.4. Xử lý cập nhật theo đợt

Nếu nhận hàng nghìn phép **cộng thêm giá trị vào đoạn** rồi chỉ xuất mảng sau tất cả cập nhật, dùng mảng hiệu có thể thực hiện mỗi cập nhật trong O(1) và kết quả cuối cùng bằng một lần cộng dồn O(n). Nhưng nếu phải trả tổng đoạn **giữa các cập nhật**, chỉ ghi mảng hiệu rồi chờ đến cuối không đủ. Phải phân biệt rõ **offline** và **online**, đặc biệt là phiên bản dữ liệu cần trả lời cho mỗi truy vấn.

## 11. Kiểm soát phiên bản và dữ liệu dẫn xuất

Một snapshot thường có mốc phiên bản, ví dụ V0, V1. Một delta cần được hiểu là **các thay đổi phát sinh sau snapshot nào**. Truy vấn phải kết hợp các phần **cùng mốc logic**.

~~~text
V0: snapshot=[5,-2,7], delta=[]
U1: set(2,10)  -> delta +3 ở index 2
Q1: sum[0,3)   -> 13
Rebase: snapshot=[5,-2,10], delta=[]
Q1 nếu hỏi lại -> vẫn 13
U2: set(0,-1)  -> delta -6 ở index 0
Q2: sum[0,3)   -> 7
~~~

Nếu snapshot đã gộp U1 thì không được cộng U1 thêm lần nữa. Nếu log sự kiện giữ nguyên để audit, phải tách **log lịch sử** khỏi **delta đang hoạt động**. Trường hợp cần hỏi dữ liệu ở một thời điểm cũ, phải giữ snapshot hoặc đủ lịch sử để khôi phục phiên bản đó; mô hình chỉ giữ trạng thái hiện tại không tự hỗ trợ truy vấn lịch sử.

Một hệ thống có nhiều người cập nhật đồng thời cần bảo đảm truy vấn không đọc một nửa trạng thái mới và một nửa trạng thái cũ. Đây là vấn đề nhất quán dữ liệu, không được giải quyết chỉ bằng việc phân chia biến base và delta.

## 12. Lỗi thường gặp

1. **Dùng prefix cũ như kết quả hiện tại:** đã sửa current nhưng chưa cộng delta/tái xây.
2. **Cộng lại sự kiện đã nằm trong snapshot mới:** đếm trùng cập nhật sau rebase.
3. **Xóa delta trước khi snapshot được cập nhật:** làm mất thay đổi từ truy vấn.
4. **Dùng `new-base` làm gia số mỗi lần sửa:** sai nếu cập nhật lặp một chỉ số. Dùng `new-current` để cộng gia số hoặc **gán** delta bằng `new-base`.
5. **Dùng int cho `new-old`:** có thể tràn trước khi gán long; ép kiểu trước phép trừ.
6. **Nhầm đoạn đóng và nửa mở:** `prefix[r]-prefix[l]` là tổng `[l,r)`, không phải đoạn đóng `[l,r]`.
7. **Quên n=0:** không có chỉ số hợp lệ để cập nhật; `sum(0,0)` có thể trả 0 theo hợp đồng.
8. **Làm lộ tham chiếu mutable tới snapshot:** mã bên ngoài sửa base khiến prefix không còn đúng.
9. **Nhầm số sự kiện với số vị trí còn thay đổi:** cập nhật có thể triệt tiêu nhau.
10. **Coi kết quả min/max là tuyến tính theo delta:** `min(base+delta)` nói chung không bằng `min(base)+min(delta)`.
11. **Không cập nhật chỉ số đã sắp/nén:** thứ tự hoặc ánh xạ có thể sai khi có khóa mới.
12. **Tái xây sau mọi cập nhật mà không tính chi phí:** có thể thành O(un) với u lần sửa.
13. **Cho rằng Fenwick trên delta nhanh hơn Fenwick trực tiếp:** cùng cận O(log n); ưu thế chủ yếu là kiến trúc và tái sử dụng snapshot.
14. **Không bảo đảm tính nhất quán khi nhiều luồng:** một truy vấn có thể đọc prefix và delta khác phiên bản.

## 13. Kiểm thử theo bất biến

Nên giữ một mảng tham chiếu cập nhật trực tiếp rồi so sánh kết quả mọi truy vấn của cấu trúc với tổng được tính bằng vòng lặp. Trên mảng ngắn, có thể xét tất cả cặp biên `0≤l≤r≤n`.

| Trường hợp | Thao tác | Kết quả cần kiểm chứng |
|---|---|---|
| Mảng rỗng | `sum(0,0)` | 0 |
| Một phần tử | `[7]` rồi `update(0,-2)` | Tổng -2 |
| Nhiều lần sửa cùng index | `7→10→6→7` | Delta ròng = 0 |
| Cập nhật ngoài đoạn | Sửa index 0, hỏi `[2,5)` | Tổng không đổi |
| Cập nhật trong đoạn | Sửa index 2 từ 7 thành 10 | Tổng đoạn chứa 2 tăng 3 |
| Đoạn rỗng | `sum(3,3)` | 0 |
| Rebase | Hỏi lại mọi đoạn ngay sau rebase | Tổng không đổi; delta đoạn = 0 |
| Giá trị cực trị | `MIN_VALUE→MAX_VALUE` | Gia số phải tính bằng long |
| Chỉ số sai | `update(-1,x)` hay `sum(3,2)` | Lỗi theo hợp đồng |
| Sao chép dữ liệu đầu vào | Sửa mảng ngoài sau khi tạo Index | Nội bộ không bị thay đổi |

**Gợi ý kiểm thử ngẫu nhiên:**

1. Sinh mảng ngắn với số âm, số 0 và số dương.
2. Thực hiện chuỗi cập nhật, truy vấn đoạn và rebase xen kẽ.
3. Sau mỗi thao tác, chọn nhiều đoạn và so `sum(l,r)` với tổng quét từ mảng tham chiếu.
4. Kiểm tra luôn `sum(l,r)=staticPart(l,r)+deltaPart(l,r)`.
5. Ngay sau rebase, mọi `deltaPart(l,r)` phải bằng 0.
6. Thử cập nhật lặp, hoàn tác, mảng rỗng, một phần tử và biên số int.

Bài kiểm thử này có khả năng phát hiện lỗi cập nhật sai dấu, cộng lặp, sai biên Fenwick và lỗi sau tái xây. Kiểm thử không thay cho chứng minh, nhưng giúp xác nhận cài đặt có giữ bất biến trên nhiều trạng thái trung gian.

## 14. Checklist trước khi thiết kế

- Phần nào của dữ liệu thật sự **bất biến** trong giai đoạn truy vấn?
- Cập nhật được phép là thay **điểm**, cộng **đoạn**, thêm/xóa phần tử, đổi tập khóa hay đổi quan hệ thứ tự?
- Kết quả tiền xử lý có phụ thuộc vào phần động không? Nếu có, cần cập nhật hay xây lại gì?
- Phép truy vấn có cho phép tách **kết quả cơ sở + hiệu chỉnh** một cách toán học không?
- Các cập nhật lặp một chỉ số được biểu diễn bằng **gia số** hay **delta ròng**?
- Một truy vấn cần thấy **phiên bản dữ liệu nào**? Log có chứa những sự kiện đã gộp vào snapshot không?
- Số phần tử n, số cập nhật u, số truy vấn q và ngân sách RAM có ủng hộ tiền xử lý không?
- Có cần tái xây định kỳ không, và chi phí tái xây đã được tính vào tổng thời gian chưa?
- Đã thử mảng rỗng, đoạn rỗng, cập nhật lặp, hoàn tác và tràn `int` chưa?
- Có truy cập đồng thời không? Nếu có, các phần base/prefix/delta/current được đồng bộ ra sao?

**Kết luận:** tách dữ liệu tĩnh khỏi dữ liệu thay đổi chỉ có ý nghĩa khi **snapshot, delta và kết quả dẫn xuất được định nghĩa bằng bất biến nhất quán**. Với tổng đoạn, ta có thể dùng tiền tố tĩnh cộng tổng các hiệu chỉnh động; với những phép toán không có cách tách tương ứng, cần một cấu trúc động khác hoặc tái tiền xử lý. Lựa chọn đúng luôn dựa trên **hợp đồng cập nhật, truy vấn và tổng chi phí thực tế**.