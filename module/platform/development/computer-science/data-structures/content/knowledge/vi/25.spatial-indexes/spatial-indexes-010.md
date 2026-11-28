# Dữ liệu lệch, cập nhật động và sự suy giảm hiệu quả của chỉ mục

Một chỉ mục không gian có thể trả truy vấn rất nhanh trên bộ dữ liệu thử nghiệm phân bố đều, nhưng chậm bất ngờ khi được đưa vào hệ thống thật. Các cảm biến thường tụ quanh khu dân cư, phương tiện liên tục đổi vị trí, những hình chữ nhật tòa nhà có kích thước chênh nhau hàng nghìn lần, còn người dùng lại thường hỏi đúng các khu vực đông đúc. Những tình huống ấy làm thay đổi **số nhánh cần mở**, **mức độ chọn lọc của vùng bao** và **chi phí bảo trì cấu trúc**.

Điều đáng chú ý là một chỉ mục có thể **vẫn trả kết quả đúng** nhưng mất phần lớn lợi thế so với quét tuần tự; ngược lại, một cập nhật làm hỏng bất biến vùng bao có thể khiến truy vấn nhanh hơn vì **bỏ sót dữ liệu**. Phân biệt hai tình huống này là kỹ năng cốt lõi khi thiết kế và vận hành hệ thống dùng k-d tree, quadtree, R-tree, grid hay spatial hash.

Bài thuộc chương **Chỉ mục không gian** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**: xây dựng nền tảng cấu trúc dữ liệu thông qua **bất biến, thao tác và độ phức tạp thời gian–bộ nhớ**, từ đó chọn cấu trúc phù hợp với bài toán. Nội dung đi từ các dạng **phân bố lệch**, tác động đến từng họ chỉ mục, thao tác chèn–xóa–di chuyển, chiến lược **rebuild và chỉ mục hai tầng**, cho tới cách đánh giá độ trễ và mã Python kiểm chứng.

> **Nguyên tắc xuyên suốt:** Phải duy trì **tính đúng** của bất biến trước, sau đó mới tối ưu **khả năng cắt tỉa**. Hộp bao quá rộng có thể làm chậm; hộp bao quá nhỏ, không chứa đủ dữ liệu, có thể gây trả thiếu.

## 1. Đặt bài toán: chỉ mục nhanh khi nào?

Cho tập bản ghi không gian:

\[
P=\{(id_i,p_i)\mid i=1,\ldots,n,\ p_i\in\mathbb R^d\}.
\]

Mỗi ID định danh một **bản ghi duy nhất**, nhưng nhiều ID có thể có tọa độ giống hệt. Một workload được xác định bởi tập dữ liệu **và phân bố thao tác**, chẳng hạn:

- **Range reporting:** tìm ID của các điểm trong cửa sổ \(Q\).
- **Range counting:** đếm số bản ghi thuộc \(Q\).
- **Nearest neighbor (NN):** tìm bản ghi gần \(q\) nhất theo metric đã định nghĩa.
- **kNN hoặc radius:** tìm k bản ghi gần nhất hoặc tất cả bản ghi trong bán kính \(r\).
- **Insert/delete/move:** thêm, xóa hoặc thay vị trí một ID.
- **Query mix:** tỷ lệ giữa các kiểu truy vấn và tỷ lệ đọc/ghi.

Với quét tuần tự, một truy vấn range hoặc 1-NN trên điểm d chiều thường cần:

\[
\boxed{O(nd)}
\]

phép kiểm tra tọa độ/khoảng cách; đổi lại dữ liệu có thể nằm trong **mảng liên tiếp**, rất thân thiện với cache và dễ cập nhật.

Chỉ mục không gian tạo metadata (mặt chia, ô, MBR, AABB, bucket) để **không phải xét mọi bản ghi**. Hiệu quả phụ thuộc vào việc các metadata này có **loại được phần lớn dữ liệu trên truy vấn thật** hay không.

### Thời gian truy vấn không chỉ phụ thuộc n

Hai hệ thống cùng \(n=1\,000\,000\) điểm có thể khác xa về độ trễ nếu:

- Hệ thống A: điểm rải đều trên bản đồ; Q nhỏ chỉ giao vài vùng.
- Hệ thống B: 900.000 điểm tụ trong một quảng trường; phần lớn Q hỏi quanh quảng trường.

Ở B, chỉ mục không thể tránh công việc **xuất hàng trăm nghìn kết quả** nếu Q nhận gần như mọi điểm trong cụm:

\[
\boxed{T_{\mathrm{report}}=\Omega(k)}
\]

với \(k\) ID thực sự được trả. Chỉ số **số kết quả** phải được tách khỏi **số node/bucket duyệt dư** khi đánh giá hiệu năng.

## 2. “Dữ liệu lệch” gồm những dạng nào?

**Skew** là sự không đồng đều theo không gian, thời gian, kích thước đối tượng hoặc mẫu truy vấn. Không có một phép đo duy nhất đại diện cho mọi skew.

| Dạng lệch | Ví dụ | Hệ quả hay gặp |
| --- | --- | --- |
| **Cluster skew** | 95% cảm biến tập trung trong một quận | Bucket nóng, quadtree chia sâu, NN/range thăm nhiều ứng viên trong cụm |
| **Hotspot truy vấn** | 80% request hỏi cùng một khu vực nhỏ | Một vài node bị đọc lặp lại, p99 phụ thuộc vùng nóng |
| **Outlier** | Vài cảm biến ở rất xa những cảm biến còn lại | MBR/root extent trải rộng, nhiều vùng trống |
| **Duplicate coordinates** | Hàng nghìn ID ở đúng (10,10) | Không thể chia riêng bằng đường hình học; phải xử lý cùng vị trí |
| **Anisotropy** | Mọi điểm nằm gần một đường thẳng | Chia theo trục không phù hợp tạo nhiều nhánh kém chọn lọc |
| **Object-size skew** | Hầu hết object nhỏ, vài đường rất dài | MBR lớn kéo rộng nhóm, tăng overlap trong R-tree |
| **Temporal skew** | Sáng đông ở trung tâm, tối đông ngoại ô | Chỉ mục tĩnh tối ưu cho phân bố cũ |
| **Update skew** | 90% bản ghi di chuyển liên tục trong một ô | Bucket churn, split/merge, contention |
| **Query-shape skew** | Q cực dài/mảnh hoặc bán kính rất lớn | Giao nhiều ô/MBR dù số điểm hợp lệ có thể ít |
| **Dimensional skew** | Nhiều chiều gần hằng số, vài chiều có độ trải lớn | Trục chia hoặc khoảng cách cần chọn/thang đo đúng |

### Skew dữ liệu khác skew truy vấn

Một tập dữ liệu không đồng đều vẫn có thể rất dễ tìm nếu người dùng thường hỏi **vùng thưa**. Ngược lại, dữ liệu nhìn tương đối đều nhưng có **một ô bị hỏi liên tục** vẫn tạo hotspot về CPU, cache, khóa và I/O.

Vì vậy cần đo riêng:

\[
\boxed{\text{phân bố dữ liệu} \ne \text{phân bố truy vấn} \ne \text{phân bố cập nhật}.}
\]

### Lệch dữ liệu không nhất thiết là lỗi

Một cảm biến ở xa cụm chính là **outlier thật**, không phải bản ghi cần tự động xóa. Một nghìn ID cùng tọa độ có thể là các bản ghi độc lập hợp lệ. Cấu trúc phải **chứa và truy vấn đúng** các trường hợp này; tối ưu chỉ được quyết định cách lưu, nhóm và định tuyến.

## 3. Hai trục đánh giá: tính đúng và hiệu suất

Khi thấy truy vấn chậm hoặc kết quả khác mong đợi, kiểm tra hai nhóm bất biến độc lập.

### 3.1. Bất biến tính đúng

Với một nhánh v và miền bao \(B_v\):

\[
\boxed{\forall p\in\operatorname{subtree}(v):p\in B_v.}
\]

Nếu là R-tree chứa hình học có diện tích, yêu cầu tương ứng là MBR node **bao toàn bộ hình học/MBR đối tượng dưới nhánh**.

Với cửa sổ truy vấn Q, chỉ được bỏ nhánh khi chứng minh:

\[
\boxed{B_v\cap Q=\varnothing.}
\]

Nếu \(B_v\) sai và không bao đủ dữ liệu, phép cắt tỉa có thể bỏ mất một kết quả thật.

Tương tự, cấu trúc định tuyến bằng split key phải duy trì vị trí đúng theo khóa; quadtree phải giữ điểm trong miền ô theo quy tắc biên; ID không được tự xuất hiện hai lần hoặc biến mất sau chèn/xóa.

### 3.2. Chỉ số hiệu quả

| Chỉ số | Phản ánh điều gì? |
| --- | --- |
| Node visits \(V\) | Bao nhiêu node phải mở |
| Entry/point tests | Bao nhiêu bản ghi thực phải kiểm tra |
| Pruned subtrees | Bao nhiêu nhánh được bỏ theo cận hợp lệ |
| Số node rỗng/đơn nhánh | Overhead cấu trúc vì miền phân hoạch lệch |
| Chiều cao h | Số cấp trên một đường đi |
| Bucket occupancy | Mức độ tập trung theo ô |
| MBR overlap/coverage | Mức duyệt nhiều nhánh và vùng bao thừa |
| p50/p95/p99 | Độ trễ thông thường và các truy vấn xấu |
| Thời gian/byte cho update và rebuild | Giá duy trì hiệu năng |
| Số bản ghi hợp lệ k | Giới hạn dưới do đầu ra |

**Một chỉ mục có V cao nhưng kết quả đúng** đang gặp vấn đề tối ưu. **Một chỉ mục có V thấp bất thường nhưng bỏ sót ID** đang gặp lỗi tính đúng, không được tính là tăng tốc thành công.

## 4. K-d tree: trung vị tĩnh không đồng nghĩa cập nhật động cân bằng

Một **k-d tree tĩnh** có thể chọn trung vị của tập điểm theo một trục ở mỗi node. Nếu chọn median chính xác:

\[
\boxed{|S_L|\approx|S_R|,}
\]

và chiều cao lúc xây là \(O(\log n)\) với mỗi node chứa một pivot.

### Phân bố lệch khi xây từ đầu

Nếu 90% điểm nằm rất gần nhau và 10% ở xa, **median vẫn cân số bản ghi**, dù **miền hình học** được tạo có thể rất méo. Vậy:

- Không nên nói “dữ liệu tập trung tự động khiến median k-d tree tĩnh lệch chiều cao”.
- Nên nói “dữ liệu tập trung có thể làm **AABB/mặt chia kém chọn lọc**, hoặc các cell quá dài/hẹp, khiến truy vấn NN/range phải mở nhiều nhánh”.

**Cân bằng số node** và **chặt về hình học** là hai tính chất khác nhau.

### Sau nhiều lần chèn

Giả sử k-d tree ban đầu dựng theo median, sau đó chèn một loạt điểm mới bằng cách đi trái/phải theo khóa split sẵn có mà **không rebuild**. Số bản ghi dưới các node có thể không còn cân; một nhánh nhận rất nhiều điểm mới.

Với một cách chèn không có cơ chế cân bằng, chiều cao trong trường hợp xấu có thể tăng tới:

\[
\boxed{h=\Theta(n)}
\]

trong đó n là tổng số điểm hiện có.

Khi ấy thao tác chèn hoặc truy tìm một điểm theo split key có thể đi qua một đường rất dài. 1-NN exact còn có thể phải **quay lại nhiều nhánh**, nên không thể mặc định chỉ tốn \(O(h)\) cho mọi truy vấn.

### Một ví dụ trên trục x

Ban đầu có các tọa độ \((0,0),(4,0),(8,0)\), pivot gốc có thể là x=4. Sau đó chèn \((9,0),(10,0),(11,0),\ldots\) bằng split key và luân phiên trục x/y. Vì mọi y đều bằng 0, nếu tie theo ID hoặc luôn đẩy về một phía mà không cân bằng lại, các điểm mới có thể dồn vào một đường đi dài.

**Kết luận chính xác:** Cơ chế chèn quyết định mức lệch. **Không phải mọi biến thể k-d tree động đều tự động suy biến**, nhưng chỉ dùng nguyên pivot tĩnh không tạo bảo đảm cân bằng dưới cập nhật bất lợi.

### Khi nào nên rebuild?

Các tín hiệu gồm chiều cao tăng mạnh so với \(\log_2(n+1)\), tỷ lệ node thăm/điểm tăng, số nhánh bị prune giảm, hoặc phân bố cập nhật liên tục dồn vào một vùng. Rebuild cân bằng lại **số điểm**, song không thể chữa mọi nhược điểm của dữ liệu nhiều chiều hay truy vấn có k rất lớn.

## 5. Quadtree: vùng nóng, chuỗi đơn nhánh và điểm trùng

Trong **PR-quadtree**, một node quản lý một miền hình chữ nhật. Khi một bucket chứa quá nhiều điểm, miền ấy được chia thành bốn phần tư (ở 2D) theo **trung điểm hình học**, không theo median của tọa độ dữ liệu.

### Điểm tập trung tạo nhiều cấp

Xét miền gốc \([0,1024)\times[0,1024)\). Nếu 10.000 điểm đều nằm trong hình vuông \([1,2)\times[1,2)\), các bước chia đầu sẽ liên tục đưa mọi điểm vào **góc dưới trái**:

~~~text
Root: [0,1024) × [0,1024)       10.000 điểm ở SW
  SW: [0,512) × [0,512)         10.000 điểm ở SW
    SW: [0,256) × [0,256)       10.000 điểm ở SW
      ...
          SW: [0,2) × [0,2)     vẫn phần lớn điểm
~~~

Những node phía trên **không giúp chia nhỏ số điểm** mặc dù làm tăng độ sâu. Đây là nguyên nhân quadtree không nén có thể sinh nhiều **chuỗi node một con**.

**Compressed quadtree** có thể nén những đoạn chỉ một nhánh, giảm số node phải đi qua mà vẫn giữ thông tin miền. Một lựa chọn khác là chọn miền gốc sát dữ liệu hơn nếu bài toán cho phép.

### Những điểm có tọa độ giống hệt

Giả sử 5.000 ID đều ở \((3,3)\). Dù chia ô bao nhiêu cấp, tất cả vẫn đi vào **cùng một ô con**:

\[
\boxed{p_i=(3,3)\quad\forall i.}
\]

Không thể giải quyết bằng cách “chia đến khi mỗi lá có tối đa một điểm” mà không có **ngoại lệ hoặc quy tắc dừng**.

Các lựa chọn hợp lệ:

- **Bucket chứa nhiều ID** tại cùng một tọa độ.
- **Gộp theo vị trí**, mỗi vị trí giữ danh sách ID riêng.
- Giới hạn độ sâu **maxDepth** hoặc kích thước ô nhỏ nhất.
- **Nén chuỗi một con**, kết hợp bucket cho tọa độ trùng.

Không được tự gộp 5.000 ID thành một **bản ghi duy nhất** nếu truy vấn yêu cầu trả đầy đủ ID.

### Biên ô và cập nhật

Với quy tắc nửa mở \([lo,hi)\), điểm đúng đường chia được định tuyến về **một ô** theo luật cố định. Sau khi di chuyển từ ô A sang ô B, phải:

1. Xóa ID khỏi bucket cũ.
2. Chèn ID vào bucket mới.
3. Cập nhật số lượng điểm ở các tổ tiên.
4. Chia nếu bucket mới vượt ngưỡng, hoặc gộp khi bucket cũ đủ thưa.

Nếu chỉ sửa tọa độ trong bucket cũ rồi để ID ở **ô không còn chứa nó**, phép prune theo miền ô có thể **trả thiếu**; đây là lỗi bất biến, không đơn giản là suy giảm tốc độ.

### Gộp để tránh dao động

Nếu capacity của bucket là 8, dùng đúng một ngưỡng “vượt 8 thì split, xuống 8 thì merge” có thể khiến hai thao tác cập nhật luân phiên tạo **split–merge liên tục** (*thrashing*). Một chính sách có **hysteresis** có thể chia khi \(occupancy>8\) nhưng chỉ gộp khi tổng số điểm dưới các con \(\le4\), chẳng hạn. Hai ngưỡng phải được mô tả rõ và không được làm sai dữ liệu.

## 6. Spatial grid/hash: công thức ô rẻ nhưng bucket có thể rất đông

Với ô vuông cạnh \(s>0\), điểm \((x,y)\) thuộc bucket:

\[
\boxed{
i=\left\lfloor\frac{x-o_x}{s}\right\rfloor,\qquad
j=\left\lfloor\frac{y-o_y}{s}\right\rfloor.
}
\]

Một **spatial hash** thường ánh xạ khóa \((i,j)\) tới danh sách/tập các ID trong ô. Nếu hash table hoạt động tốt, việc tìm bucket có thể \(O(1)\) **trung bình**. Nhưng tìm một ID cụ thể trong bucket còn phụ thuộc cách lưu các ID.

### Occupancy skew

Giả sử n=1.000.000 điểm, có 10.000 bucket không rỗng, nhưng một bucket chứa 300.000 điểm. Mức trung bình là:

\[
\frac{n}{10\,000}=100,
\]

nhưng bucket nóng chứa **3.000 lần trung bình**. Một truy vấn nhỏ cần kiểm tra tất cả bản ghi trong bucket đó có thể chậm gần như quét một phần đáng kể dữ liệu.

Do đó **bucket trung bình** không đủ. Nên đo:

\[
\boxed{
L_{\max}=\max_{b}\operatorname{occupancy}(b),\quad
L_{95}=\operatorname{p95}\{\operatorname{occupancy}(b)\}.
}
\]

Với các bucket khác nhau, số lượng ô nóng và **phân bố truy vấn theo ô** cũng quan trọng. Một bucket đông nhưng không ai hỏi có thể ít ảnh hưởng latency hơn bucket nhỏ hơn nhưng chịu hàng triệu request.

### Grid quá thô hoặc quá mịn

**Ô lớn:** ít ô phải liệt kê nhưng nhiều điểm cùng bucket; lọc trong bucket tốn chi phí.

**Ô nhỏ:** ít điểm mỗi bucket nhưng một Q rộng phải liệt kê nhiều ô. Spatial hash thưa giảm bộ nhớ ô rỗng nhưng không tự biến việc **duyệt tọa độ hàng triệu ô** thành hằng số.

Một phân tích thô cho range Q:

\[
\boxed{T_{\mathrm{grid}}=O(c+\text{candidates}+k),}
\]

với c ô được liệt kê và candidates là số ID được kiểm tra tại các bucket ấy. Hằng số phụ thuộc cách tra hash, duyệt mảng và khả năng bỏ qua ô rỗng.

### Di chuyển qua ranh giới

Với \(s=4\) và gốc ở 0:

- Điểm \((3.9,2)\) thuộc ô \((0,0)\).
- Điểm \((4.0,2)\) thuộc ô \((1,0)\).

Một chuyển động rất nhỏ vẫn có thể gây **xóa và chèn bucket**. Với hàng triệu vật thể dao động ngay biên, số lượng update có thể lớn. Có thể giảm bằng cách chọn ô lớn hơn, lưu vùng đệm theo thiết kế khác, hoặc cập nhật batch; nhưng **không được giữ ID ở ô sai** nếu query dựa trên phân hoạch chính xác.

### Tọa độ âm

Với \(s=4\), điểm x=-0.1 thuộc ô \(\lfloor-0.1/4\rfloor=-1\), **không phải** ô 0. Nếu dùng phép chuyển sang integer cắt về 0 thay vì floor, cấu trúc có thể đặt điểm sai ô và trả thiếu kết quả.

## 7. R-tree: MBR chồng lấn và đối tượng có kích thước rất khác

R-tree không định tuyến điểm bằng một mặt chia cố định. Nó nhóm các object-entry theo **minimum bounding rectangle** (MBR). Hai child-MBR của cùng node có thể **chồng lấn**, dù ID của hai nhóm khác nhau.

### Overlap tăng số nhánh phải mở

Cho:

\[
B_A=[0,6]\times[0,6],\qquad
B_B=[4,10]\times[4,10].
\]

Với \(Q=[4.5,5.5]\times[4.5,5.5]\), Q giao **cả hai MBR**. Truy vấn phải xem cả hai nhánh, dù chỉ một nhánh hoặc không nhánh nào chứa object thật giao Q.

Trong trường hợp xấu, nhiều MBR cùng giao Q, khiến số node thăm tăng mạnh:

\[
\boxed{T_{\mathrm{range}}=O(V+E_V+k_c T_{\mathrm{refine}}+k),}
\]

với \(V\) node thăm, \(E_V\) entry kiểm tra, \(k_c\) ứng viên MBR giao Q và \(k\) kết quả cuối. Nếu object là hình chữ nhật 2D, bước refine có thể là \(O(1)\); nếu object là polygon phức tạp, bước kiểm tra hình thật có thể tốn nhiều hơn.

### Outlier và đối tượng rất lớn

Một đối tượng dài từ góc dưới trái đến góc trên phải có MBR gần bằng toàn miền. Nếu đưa object ấy vào một nhóm, MBR nhóm phải **bao trọn object**, nên vùng bao có thể kéo dài qua rất nhiều khoảng trống.

**Không thể split tốt để tạo MBR nhóm nhỏ hơn chính object mà nhóm chứa.** Một phần độ chồng lấn là do dữ liệu, không phải do một triển khai ChooseSubtree thiếu khéo.

### Phân bố và thứ tự chèn

R-tree cơ bản thường chọn nhánh bằng **độ tăng diện tích**:

\[
\boxed{
\Delta A(R,E)=\operatorname{area}(\operatorname{cover}(R,E))
-\operatorname{area}(R).
}
\]

Sau overflow, node được split, chẳng hạn bằng **quadratic split**, thành hai nhóm đảm bảo min-fill. Vì quyết định dựa vào **trạng thái hiện tại của cây**, việc chèn cùng dữ liệu theo hai thứ tự khác nhau có thể tạo MBR overlap và hiệu năng query khác nhau.

**R\*-tree** có thêm chiến lược quan tâm overlap/margin và forced reinsertion; **STR bulk loading** có thể nhóm dữ liệu tĩnh theo không gian trước khi tạo node. Các phương án này **có thể** cải thiện hiệu năng nhưng không bảo đảm thắng mọi phân bố.

### MBR rộng và MBR sai khác nhau

Với hộp Q, nếu child-MBR **không giao** Q, bỏ nhánh là hợp lệ chỉ khi MBR chứa **tất cả đối tượng bên dưới**.

- **MBR rộng quá mức**: vẫn bao đúng → nhiều false-positive candidates, truy vấn chậm.
- **MBR bị thu nhỏ thiếu object**: không bao đủ → false negative, truy vấn sai.

Nếu object di chuyển ra ngoài MBR cha cũ mà không cập nhật MBR tổ tiên, R-tree có thể âm thầm bỏ mất object dù ID vẫn tồn tại trong lá.

## 8. Bảng so sánh tác động của skew và update theo cấu trúc

| Tình huống | K-d tree median | PR-quadtree | Spatial hash/grid | R-tree |
| --- | --- | --- | --- | --- |
| Điểm dồn vào một cụm | Cân số ID khi build; AABB/cell có thể kém chọn lọc | Một chuỗi ô sâu hoặc bucket dày | Một vài bucket cực đông | MBR nhóm có thể lớn/chồng lấn |
| Cùng tọa độ, nhiều ID | Có thể tie bằng ID trong pivot | Cần bucket ngoại lệ/dừng độ sâu | Một bucket chứa nhiều ID | Các MBR suy biến cùng vị trí, nhiều leaf-entry |
| Outlier xa | AABB root rộng; pivot vẫn cân số ID | Root extent rộng, nhiều cấp đơn nhánh | Hash thưa không cần toàn miền | MBR lớn kéo rộng nhóm |
| Chèn theo một phía | Cây động đơn giản có thể lệch chiều cao | Tạo thêm nhánh sâu ở vùng nóng | Bucket bên đó tăng | Split, MBR cập nhật và overlap thay đổi |
| Di chuyển liên tục | Cần giữ split key/AABB, thường remove+insert | Đổi ô, split/merge | Chuyển bucket | Cập nhật/xóa-chèn, có thể split/condense |
| Truy vấn rất rộng | Phải xuất nhiều ID | Phải xuất nhiều ID | Liệt kê nhiều ô và ID | Mở nhiều MBR và xuất nhiều object |
| NN với vùng bao lỏng | Quay lại nhiều nhánh | Thăm nhiều ô | Mở rộng nhiều vòng ô | Mở nhiều MBR chồng lấn |
| Rebuild có lợi khi | Chiều cao hoặc node visits tăng | Quá nhiều chuỗi một con / root không hợp lý | Cell size lỗi thời | Nhóm MBR overlap, underfill hoặc phân bố mới |

**Bảng chỉ mô tả rủi ro, không phải định lý thứ tự nhanh/chậm.** Chất lượng cấu trúc còn phụ thuộc kích thước bucket/ô, fanout, số chiều, thứ tự chèn, khả năng nén, cache và bộ dữ liệu thực.

## 9. Phân biệt bốn loại suy giảm khi vận hành

Khi đo hiệu năng, cần gọi đúng tên vấn đề để chọn giải pháp hợp lý.

### (A) Cấu trúc bị lệch

Số node trên đường đi tăng bất thường, chẳng hạn k-d tree động không cân bằng hay quadtree có chuỗi ô đơn nhánh dài. Một rebuild/cân bằng lại có thể giảm **độ sâu**.

### (B) Vùng bao kém chọn lọc

Chiều cao cây vẫn nhỏ, nhưng AABB/MBR của nhiều nhánh giao Q hoặc có minDist thấp. Truy vấn mở quá nhiều nhánh. Rebuild chỉ có ích nếu nhóm mới **làm vùng bao chặt hơn**; nó không giúp khi phần lớn các object thật cùng giao Q.

### (C) Tồn tại nhiều bản ghi “không còn sống”

Delete theo kiểu **tombstone** có thể để lại nhiều pivot/entry trong chỉ mục cơ sở. Nếu chưa loại vật lý hoặc chưa rebuild, truy vấn vẫn duyệt các vùng có nhiều bản ghi đã xóa. Chúng có thể làm AABB/MBR **rộng hơn cần thiết** dù kết quả đã được lọc đúng theo ID.

### (D) Workload không còn phù hợp cấu hình

Grid từng dùng ô cạnh 100 m khi số điểm rất ít, nay mật độ tăng gấp trăm lần; hoặc người dùng chuyển từ truy vấn cửa sổ nhỏ sang quét cả thành phố. Lúc ấy **đổi tham số, cấu trúc hoặc chiến lược cache** có thể quan trọng hơn việc rebuild với thông số cũ.

| Triệu chứng | Cần đo | Hướng xử lý |
| --- | --- | --- |
| Đường đi k-d tree dài | Height, histogram độ sâu, số node thăm | Rebuild median hoặc thay cấu trúc động |
| Quadtree có nhiều node một con | Tỷ lệ single-child, max depth | Compression, root extent, maxDepth/bucket |
| Một ô hash cực đông | Max/p95 occupancy | Điều chỉnh s, chia bucket nóng, hybrid |
| R-tree mở nhiều nhánh | Sibling overlap, branch forks, page reads | R\*-tree, bulk load/reinsert, rebuild |
| Tombstone nhiều | Tỷ lệ deleted/base, node thăm không sinh kết quả | Compaction/rebuild |
| Query đúng nhưng p99 tăng | Phân bố Q, k, vùng truy cập và lock wait | Tối ưu theo hotspot, cache, chọn chỉ mục |
| Query thiếu ID | Validate bbox, split key, consistency/version | **Sửa lỗi bất biến trước tối ưu** |

## 10. Ngữ nghĩa update: một ID, một trạng thái hiện hành

Với chỉ mục động, phải định nghĩa nhất quán cách xử lý bản ghi và ID. Một quy ước đơn giản:

- **Insert(id,p):** thêm ID mới; nếu ID đã tồn tại thì từ chối.
- **Upsert(id,p):** thêm nếu chưa có, còn nếu đã có thì thay tọa độ cũ bằng p.
- **Delete(id):** xóa ID hiện hành; xóa ID không tồn tại có thể trả False hoặc lỗi theo API.
- **Move(id,p):** yêu cầu ID đã tồn tại, thay tọa độ hiện tại bằng p.

Sau mỗi thao tác thành công, tập dữ liệu logic phải là **một ánh xạ**:

\[
\boxed{\mathcal D:\operatorname{ID}\mapsto\operatorname{coordinates}.}
\]

Một ID không được cùng lúc xuất hiện ở hai vị trí khác nhau trong kết quả truy vấn.

### Ví dụ sai sau khi di chuyển

Ban đầu:

~~~text
sensor-7 -> (2,2)      nằm trong bucket A
~~~

Sau Move(sensor-7,(20,20)), nếu hệ thống **chỉ thêm** bản ghi mới ở bucket B mà không xóa/che bản ghi cũ:

~~~text
bucket A: sensor-7 -> (2,2)        [stale]
bucket B: sensor-7 -> (20,20)      [current]
~~~

Một range query có thể trả cùng ID hai lần hoặc trả ID ở vị trí không còn đúng. Đây là **lỗi nhất quán logic**, không chỉ là vấn đề hiệu năng.

### Thứ tự cập nhật và phiên bản

Nếu dùng cơ chế nhiều bản ghi phiên bản, phải có quy tắc xác định **phiên bản mới nhất có hiệu lực**. Ví dụ:

\[
\boxed{
\operatorname{visible}(id)=
\text{phiên bản hợp lệ mới nhất theo snapshot truy vấn}.
}
\]

Chỉ “khử trùng ID” sau khi trả kết quả không đủ nếu nó vô tình giữ **tọa độ cũ**. Phiên bản mới nhất cần chi phối cả **predicate hình học** và **tie-break của NN**.

### Cập nhật nguyên tử với truy vấn đồng thời

Nếu Move là hai bước “xóa cũ” rồi “chèn mới”, một truy vấn đọc xen giữa có thể thấy ID tạm thời **biến mất**. Nếu “chèn mới” trước “xóa cũ”, nó có thể thấy ID **hai lần**.

Một hệ thống cần tính nhất quán phải dùng giao dịch, khóa, snapshot, copy-on-write hoặc một giao thức phiên bản rõ ràng. Ví dụ Python ở phần sau chỉ chứng minh tính đúng trong chế độ **tuần tự**, không mô phỏng atomic multi-thread.

## 11. Xóa lười và tombstone: tiện cập nhật nhưng làm chỉ mục phình

**Lazy deletion** nghĩa là đánh dấu bản ghi đã bị xóa thay vì ngay lập tức tái cấu trúc cây. Một tập **tombstone IDs** cho biết những ID của cây cơ sở không được trả ra nữa.

### Tại sao không xóa trực tiếp?

Với k-d tree, xóa một pivot có thể đòi xử lý cây con để vẫn bảo đảm split key. Với R-tree, xóa có thể gây underflow và phải CondenseTree. Với dữ liệu cập nhật liên tục, việc đẩy phần bảo trì này sang **rebuild định kỳ** đôi khi tiết kiệm tổng chi phí.

### Nguyên tắc lọc

Tại lúc truy vấn, một bản ghi thuộc chỉ mục cơ sở chỉ được trả nếu:

\[
\boxed{id\notin Tombstones}
\]

và **không bị phiên bản cập nhật mới ghi đè** trong delta.

**Quan trọng:** Nếu ID đã được di chuyển, bản ghi cũ không được dùng như một ứng viên NN để cập nhật best; làm vậy có thể **cắt nhánh khác sai** dù kết quả cuối cố khử trùng ID.

### Tombstone làm AABB quá rộng nhưng vẫn an toàn

Giả sử AABB cây con ban đầu:

\[
B=[0,100]\times[0,100].
\]

Sau khi xóa hết các điểm xa, dữ liệu còn sống chỉ trong \([0,10]\times[0,10]\). Nếu vẫn dùng B cũ:

- B **vẫn bao tất cả điểm còn sống**, nên prune theo B không gây false negative.
- B rộng hơn AABB chặt, nên có thể làm nhiều truy vấn **duyệt dư**.

Một lần rebuild từ điểm còn sống có thể tính lại AABB chặt hơn và bỏ bản ghi chết.

### Đếm dữ liệu có tombstone

Nếu node đang lưu subtree size=1.000 nhưng 600 ID đã xóa, không được cộng trực tiếp 1.000 cho range counting khi Q chứa trọn AABB. Size phải là **số ID còn sống được nhìn thấy ở phiên bản truy vấn**, hoặc truy vấn phải bù trừ số tombstone/ID bị ghi đè chính xác.

Đây là một lý do cơ chế tombstone cần thống kê/aggregate đúng hoặc định kỳ compact; không chỉ là một bit “đã xóa” độc lập.

## 12. Chỉ mục cơ sở + delta: tách phần tĩnh và phần cập nhật

Một cách tổ chức giúp giữ hiệu năng dưới cập nhật là dùng hai tầng:

1. **Base index:** một chỉ mục tĩnh xây từ tập điểm tại lần rebuild gần nhất.
2. **Delta map/index:** chứa bản ghi mới hoặc phiên bản cập nhật mới của một ID.
3. **Tombstone set:** chứa những ID thuộc base đã bị xóa về mặt logic.

Khi upsert một ID đang có trong base, delta **ghi đè** bản base cùng ID; khi xóa, bản base cần bị **che đi** ngay cả nếu trước đó ID từng nằm trong delta.

### Bất biến hiển thị dữ liệu

Gọi \(B\) là ánh xạ base, \(\Delta\) là ánh xạ delta và \(T\) là tombstones. Khi đó dữ liệu hiện hành:

\[
\boxed{
\mathcal D =
\{(id,B[id]):id\in B,\ id\notin T,\ id\notin\Delta\}
\;\cup\;
\{(id,\Delta[id]):id\in\Delta\}.
}
\]

Ta yêu cầu mỗi ID trong \(\mathcal D\) xuất hiện **đúng một lần**. Nếu dùng mô hình này, thao tác upsert phải bảo đảm rằng ID có trong delta không bị xem như tombstone ngăn cả phiên bản delta.

### Phác thảo luồng update

~~~text
UPSERT(id, p):
    delta[id] = p         // Phiên bản này thắng bản base.
    tombstones.remove(id) // Nếu tồn tại, bỏ dấu xóa cũ.
    MAYBE_REBUILD()

DELETE(id):
    nếu ID không có trong dữ liệu hiện hành: return False
    nếu ID có trong delta: xóa entry delta[id]
    nếu ID có trong base: tombstones.add(id)
    MAYBE_REBUILD()
    return True
~~~

### Truy vấn range chính xác

1. Duyệt base index, nhưng **bỏ những ID trong tombstones hoặc delta**.
2. Duyệt delta, chọn bản ghi có **tọa độ mới** thuộc Q.
3. Hợp các ID, chỉ trả mỗi ID một lần.

~~~text
RANGE(Q):
    out = []
    for (id,p) in BASE_RANGE(Q):
        if id not in tombstones and id not in delta:
            out.append(id)
    for (id,p) in delta:
        if p in Q:
            out.append(id)
    return sorted(out)
~~~

Không được chỉ query base rồi bổ sung delta nếu vẫn trả bản base **đã bị di chuyển ra ngoài Q**. Cũng không được chỉ hỏi delta ở những vùng AABB cũ có thể giao Q: delta **có thể đặt bản ghi mới ở bất kỳ đâu** trong miền dữ liệu cho phép.

### Truy vấn NN chính xác

1. Xét các bản ghi delta để có ứng viên tốt ban đầu.
2. Duyệt base index bằng cận minDist/AABB.
3. Không dùng bản base đã tombstone/ghi đè làm ứng viên best.
4. Chọn min theo \((distance^2,ID)\) trên **cả hai tầng**.

**Vùng bao base có thể còn các ID cũ**, nhưng vì nó vẫn bao mọi bản ghi base còn sống, phép prune dựa trên AABB base vẫn **an toàn**. Nó chỉ có thể mở nhiều node thừa do bản cũ.

### Rebuild / compaction

Khi delta và tombstone đủ lớn:

\[
\boxed{NewBase = \operatorname{BuildIndex}(\mathcal D).}
\]

Sau đó delta và tombstones được xóa khỏi **thế hệ mới**. Không được xóa chúng trước khi NewBase đã chứa tất cả thay đổi.

Trong hệ thống đồng thời, việc build trên snapshot và **chuyển thế hệ atomically** phải giải quyết mọi update phát sinh trong lúc build (ví dụ WAL/delta mới và replay hoặc snapshot version). Nếu không, việc rebuild có thể **làm mất cập nhật** dù từng lệnh insert/delete trước đó đã thành công.

## 13. Chọn thời điểm rebuild: ngưỡng kích thước, chi phí và độ trễ

Rebuild thường làm cây tốt hơn về mặt cấu trúc, nhưng có chi phí CPU, RAM, I/O và có thể gây ngừng truy vấn nếu thực hiện đồng bộ.

### Ngưỡng theo tỷ lệ pending updates

Đặt:

- \(n_B=|B|\): số ID trong base.
- \(u=|\Delta|\): số ID mới/đã cập nhật chưa compact.
- \(t=|T|\): số ID base đã tombstone.

Một chính sách đơn giản:

\[
\boxed{
\text{rebuild nếu }u+t\ge\max(u_{\min},\lceil\alpha n_B\rceil).
}
\]

Ví dụ với \(\alpha=0.25\), \(u_{\min}=8\), base có 1.000 ID: rebuild khi tổng delta và tombstones đạt ít nhất 250.

**Không phải tiêu chuẩn tối ưu phổ quát.** Nếu một ID được di chuyển một triệu lần nhưng delta chỉ giữ **phiên bản mới nhất**, \(u\) có thể vẫn bằng 1. Lúc đó không rebuild cũng có thể hợp lý: base lookup loại bản cũ bằng một phép kiểm tra ID, còn delta rất nhỏ.

### Ngưỡng theo hiệu năng thật

Một chính sách động hơn có thể rebuild khi:

- p95/p99 của nhóm truy vấn quan trọng vượt mục tiêu.
- Số node thăm trên query tăng một tỷ lệ lớn so với sau rebuild.
- Tỷ lệ ID chết, MBR rộng hoặc node đơn nhánh vượt ngưỡng.
- Bucket/nhánh nóng vượt mức tải dự kiến.
- Tổng thời gian quét delta trong các query lớn hơn chi phí amortize của rebuild.

Tránh rebuild chỉ dựa trên **một truy vấn chậm**: có thể đó là query trả k rất lớn, mà rebuild không thể loại bỏ chi phí xuất k.

### Phân tích chi phí khấu hao

Giả sử xây lại một k-d tree median bằng **sort lại tại mỗi node** có chi phí:

\[
\boxed{B(n)=O(n\log^2 n)}
\]

với số chiều d cố định. Nếu cứ sau khoảng \(\alpha n\) update khác ID mới rebuild (và n gần ổn định), chi phí rebuild khấu hao trên mỗi update xấp xỉ:

\[
\frac{B(n)}{\alpha n}
=O\left(\frac{\log^2 n}{\alpha}\right).
\]

Đây là **ước lượng với giả thiết kích thước n gần ổn định và đủ \(\alpha n\) update giữa các rebuild**. Nó **không** bao gồm chi phí truy vấn delta trong thời gian chờ, khóa cạnh tranh, chi phí bộ nhớ tạm hay các tình huống thay đổi n rất mạnh.

### Rebuild quá thường xuyên và quá thưa

| Chính sách | Lợi ích | Rủi ro |
| --- | --- | --- |
| Rebuild sau mọi update | Cấu trúc luôn được dựng lại từ trạng thái mới | CPU/I/O cực lớn, p99 update cao |
| Rebuild theo ngưỡng nhỏ | Delta nhỏ, metadata chặt | Tốn rebuild lặp lại |
| Rebuild theo ngưỡng lớn | Ít chi phí xây lại | Delta/tombstone nhiều, query chậm |
| Rebuild theo đo đạc workload | Gắn trực tiếp mục tiêu latency | Phức tạp, cần quan sát và guardrail |
| Rebuild định kỳ ban đêm | Thuận tiện tải theo lịch | Có thể stale hiệu năng nhiều giờ, spike nếu build cạnh tranh |

### Rebuild không bắt buộc thay toàn bộ cấu trúc

Các phương án cục bộ:

- **Rebuild cây con** mất cân bằng của k-d tree.
- **Compress/gộp** chuỗi quadtree đơn nhánh.
- **Split một bucket nóng** bằng cấu trúc phụ hoặc đổi grid thành multi-level grid.
- **R\*-tree reinsertion, split/bulk-load cây con** hoặc xây lại thế hệ R-tree.

Nhưng rebuild cục bộ vẫn phải bảo toàn định tuyến, MBR và ID. Một chiến lược “cân lại” chỉ vì tiết kiệm node nhưng bỏ sót điểm là không hợp lệ.

## 14. Quản lý thế hệ và tính nhất quán khi rebuild không chặn truy vấn

Trong hệ thống lớn, rebuild có thể diễn ra trong khi hàng nghìn truy vấn và update vẫn đến. Một luồng xây chỉ mục nền (*background builder*) chỉ an toàn khi dữ liệu và phiên bản được quản lý rõ ràng.

### Một thiết kế theo thế hệ

~~~text
                     CÁC UPDATE MỚI
                           |
                           v
                  +-----------------+
                  | ACTIVE DELTA    |  ID -> bản ghi mới
                  | TOMBSTONES      |  ID xóa
                  +-----------------+
                           |
               snapshot ở version V
                           |
                           v
            BUILD NEW BASE từ trạng thái ở V
                           |
            ghi nhận mọi update sau V
                           |
                           v
               MERGE/REPLAY update mới
                           |
                           v
              ATOMIC GENERATION SWAP
                           |
                           v
                  BASE MỚI + DELTA
~~~

Giả sử lúc bắt đầu build, có snapshot S tại version V. Trong lúc builder làm việc, ID A bị chuyển từ \((2,2)\) sang \((7,7)\). Nếu builder chỉ dùng snapshot rồi sau đó **xóa sạch delta**, A có thể quay về \((2,2)\), dù update mới đã thành công.

Muốn bảo đảm tính đúng, cần một trong những cơ chế như:

- **MVCC/snapshot + update log**: lưu các update sau V và replay vào delta của thế hệ mới.
- **Double-buffer delta**: đóng băng delta snapshot phục vụ build, ghi update mới vào delta khác.
- **Copy-on-write**: dựng phiên bản cây mới, giữ thế hệ cũ cho truy vấn đang chạy.
- **Khóa/transaction**: giới hạn thời điểm swap hoặc bảo đảm không có update bị rơi giữa các giai đoạn.

### Thời điểm tuyến tính hóa

Một API update nhất quán cần xác định **khi nào thay đổi được coi là đã có hiệu lực** (*linearization point*). Truy vấn trước thời điểm ấy có thể thấy phiên bản cũ, truy vấn sau phải thấy phiên bản mới theo mô hình nhất quán đã công bố.

Không nên tùy tiện “chụp danh sách ID từ base rồi tọa độ từ delta” ở những version khác nhau và coi đó là một snapshot hợp lệ.

### Rebuild có thể tăng áp lực bộ nhớ

Trong lúc xây NewBase, hệ thống có thể phải giữ **OldBase và NewBase đồng thời**, cộng thêm delta, WAL và bộ đệm. Với n điểm d chiều, bộ nhớ tức thời có thể gần gấp đôi một chỉ mục tĩnh hoặc hơn, tùy cách triển khai.

Vì vậy thời điểm và tốc độ rebuild còn phụ thuộc **RAM trống**, ngân sách I/O và khả năng cạnh tranh với truy vấn thật.

## 15. Độ lệch trong số chiều cao, tọa độ địa lý và chuyển động thực

### Không gian nhiều chiều

Trong vector 128/768 chiều, những vùng AABB có thể khó cắt tỉa: nhiều node có cận khoảng cách nhỏ, hoặc khoảng cách giữa các điểm tương đối gần nhau. Cây cân bằng về số ID **không khắc phục hoàn toàn** hiện tượng này (*curse of dimensionality*).

Nếu chấp nhận gần đúng, có thể cân nhắc **approximate nearest neighbor (ANN)** và đo recall/độ trễ. Nhưng một hệ thống được yêu cầu **exact NN** không được tự bỏ nhánh khi chưa có cận đúng.

### Kinh độ/vĩ độ

Chỉ số x/y theo **độ địa lý** không tự tương đương khoảng cách mét. Một chuyển động nhỏ qua kinh tuyến \(\pm180^\circ\) có thể tạo hiệu tọa độ longitude rất lớn nếu xử lý trực tiếp.

Với dữ liệu bản đồ, hãy xác định:

- CRS/hệ quy chiếu phù hợp.
- Đơn vị từng trục.
- Cách xử lý đường đổi ngày và cực.
- Metric cho NN/radius (Euclid trong hệ phẳng phù hợp hay khoảng cách trên mặt cầu/ellipsoid).
- Cách biểu diễn MBR qua ranh giới tuần hoàn.

Không dùng cận Euclid tính trên độ để prune cho một bài toán tối ưu khoảng cách địa lý **theo mét** nếu chưa chứng minh cận hợp lệ.

### Vật thể di chuyển và vùng bao

Một object game hoặc phương tiện có thể thay tọa độ 60 lần/giây. Cấu trúc point-index và object-index cần cân nhắc:

- Update có phải thay đổi chỉ mục sau **mọi khung hình** không?
- Bán kính tương tác và cell size có phù hợp không?
- Có cần **swept AABB** để bao chuyển động giữa hai frame không?
- Một object lớn có giao nhiều ô nhưng có thể được lưu bằng **một entry R-tree** không?

**Swept AABB** bao quỹ đạo trong một khoảng thời gian; nó rộng hơn AABB tức thời nhưng có thể là metadata đúng cho truy vấn va chạm **liên tục theo thời gian**. Không nên gọi mọi AABB rộng là “stale”: phải hỏi nó đang mô tả **trạng thái tức thời hay một khoảng thời gian**.

## 16. Chọn cấu trúc và chiến lược theo tính chất workload

| Workload | Phương án đáng thử | Nguyên nhân |
| --- | --- | --- |
| Điểm 2D tương đối tĩnh, range/NN nhiều | K-d tree median tĩnh, có AABB | Cân số ID khi build, cắt tỉa bằng hộp dữ liệu |
| Điểm di chuyển, vị trí tập trung vừa phải, hỏi lân cận trong bán kính cố định | Spatial hash/grid | Chuyển bucket đơn giản khi đổi ô |
| Mật độ điểm cực khác nhau giữa các khu | PR-quadtree có bucket/maxDepth/compression | Chia riêng vùng dày; quản lý cụm/điểm trùng |
| Nhiều hình chữ nhật/đa giác kích thước khác nhau | R-tree/R\*-tree | Dùng MBR cho broad phase, refine hình thật |
| Nhiều update nhưng query rất ít, n nhỏ | Mảng/quét tuyến tính | Tránh overhead cấu trúc và rebuild |
| Query nhiều, update theo lô | Base index tĩnh + delta + rebuild | Khai thác hiệu năng truy vấn tĩnh mà vẫn cập nhật logic nhanh |
| R-tree bị overlap sau nhiều cập nhật | Reinsert/rebuild/bulk-load hoặc R\*-tree | Thử giảm duyệt nhiều nhánh và coverage |
| Query kNN trong không gian hàng trăm chiều, chấp nhận sai số | ANN chuyên biệt | Đo recall để đổi lấy latency |
| Cần exact query dưới cập nhật đồng thời | Chỉ mục có version/snapshot/transaction | Tránh đọc trạng thái nửa cũ nửa mới |

Quyết định cuối cùng phải dựa trên **chi phí tổng**:

\[
\boxed{
C_{\mathrm{total}}
=N_q C_q
+N_u C_u
+C_{\mathrm{build}}
+C_{\mathrm{rebuild}}
+C_{\mathrm{memory/I/O}}.
}
\]

Đây là **mô hình kế toán khái niệm**, không phải công thức đơn vị đo tự động đồng nhất: cần chuẩn hóa CPU time, I/O, RAM hoặc chi phí tiền theo mục tiêu hệ thống.

## 17. Python: chỉ mục k-d tree cơ sở + delta + tombstone

Ví dụ này dùng **Python 3.10+**, thư viện chuẩn, tọa độ Euclid **2D** và thao tác **tuần tự**. Mục đích là minh họa một cách bảo trì chỉ mục trước cập nhật động mà không phải sửa pivot của cây trung vị sau mỗi lần di chuyển:

1. Tạo k-d tree tĩnh **base** bằng median split và AABB.
2. Mọi thao tác **upsert** được lưu vào **delta dictionary**.
3. Khi xóa ID thuộc base, đánh dấu **tombstone** thay vì thay trực tiếp cây.
4. Truy vấn base nhưng **bỏ ID đã xóa hoặc bị delta ghi đè**; đồng thời kiểm tra delta.
5. Khi lượng pending đủ lớn, **rebuild** từ toàn bộ ID hiện hành.

API có **upsert, insert, delete, get, range_ids, nearest_id, rebuild, stats và validate**. Mọi truy vấn range là **hộp đóng**; tie-break NN chọn ID nhỏ hơn khi bình phương khoảng cách bằng nhau. Ví dụ không cài giao dịch, concurrent snapshot, persistence hay phép hình học địa lý.

~~~python
from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite


@dataclass
class KDNode:
    id: str
    point: tuple[float, float]
    axis: int
    lo: tuple[float, float]
    hi: tuple[float, float]
    size: int
    left: KDNode | None = None
    right: KDNode | None = None


def _point(raw):
    p = tuple(float(x) for x in raw)
    if len(p) != 2 or not all(isfinite(x) for x in p):
        raise ValueError("Cần đúng hai tọa độ hữu hạn")
    return p


def _distance_sq(a, b):
    return ((a[0] - b[0]) ** 2
            + (a[1] - b[1]) ** 2)


def _min_distance_sq(q, lo, hi):
    dx = max(lo[0] - q[0], 0.0, q[0] - hi[0])
    dy = max(lo[1] - q[1], 0.0, q[1] - hi[1])
    return dx * dx + dy * dy


def _inside_closed(p, qlo, qhi):
    return (
        qlo[0] <= p[0] <= qhi[0]
        and qlo[1] <= p[1] <= qhi[1]
    )


def _bbox_intersects_closed(lo, hi, qlo, qhi):
    return not (
        hi[0] < qlo[0] or lo[0] > qhi[0]
        or hi[1] < qlo[1] or lo[1] > qhi[1]
    )


class BufferedKDIndex:
    def __init__(
        self,
        records=(),
        rebuild_fraction=0.25,
        min_pending=8,
    ):
        if (not isfinite(float(rebuild_fraction))
                or rebuild_fraction <= 0):
            raise ValueError("rebuild_fraction phải dương và hữu hạn")
        if type(min_pending) is not int or min_pending < 1:
            raise ValueError("min_pending phải là số nguyên dương")

        self.rebuild_fraction = float(rebuild_fraction)
        self.min_pending = min_pending
        self.base: dict[str, tuple[float, float]] = {}
        for item_id, coordinates in records:
            if not isinstance(item_id, str) or not item_id:
                raise ValueError("ID phải là chuỗi không rỗng")
            if item_id in self.base:
                raise ValueError("ID ban đầu bị trùng")
            self.base[item_id] = _point(coordinates)

        self.root = self._build(list(self.base.items()), depth=0)
        self.delta: dict[str, tuple[float, float]] = {}
        self.tombstones: set[str] = set()
        self.rebuild_count = 0

    @classmethod
    def _build(cls, entries, depth):
        if not entries:
            return None

        axis = depth % 2
        entries = sorted(
            entries, key=lambda item: (item[1][axis], item[0])
        )
        mid = len(entries) // 2
        item_id, p = entries[mid]

        left = cls._build(entries[:mid], depth + 1)
        right = cls._build(entries[mid + 1:], depth + 1)
        lo = [p[0], p[1]]
        hi = [p[0], p[1]]
        size = 1

        for child in (left, right):
            if child is None:
                continue
            size += child.size
            for axis_i in (0, 1):
                lo[axis_i] = min(lo[axis_i], child.lo[axis_i])
                hi[axis_i] = max(hi[axis_i], child.hi[axis_i])

        return KDNode(
            item_id, p, axis, tuple(lo), tuple(hi),
            size, left, right
        )

    def _threshold(self):
        return max(
            self.min_pending,
            ceil(self.rebuild_fraction * max(1, len(self.base))),
        )

    def _maybe_rebuild(self):
        if len(self.delta) + len(self.tombstones) >= self._threshold():
            self.rebuild()

    def get(self, item_id):
        """Tọa độ mới nhất hoặc None nếu ID đã xóa/chưa có."""
        if item_id in self.delta:
            return self.delta[item_id]
        if item_id in self.tombstones:
            return None
        return self.base.get(item_id)

    def upsert(self, item_id, raw_point):
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("ID phải là chuỗi không rỗng")
        p = _point(raw_point)
        self.delta[item_id] = p
        self.tombstones.discard(item_id)
        self._maybe_rebuild()

    def insert(self, item_id, raw_point):
        if self.get(item_id) is not None:
            raise ValueError("ID đã tồn tại")
        self.upsert(item_id, raw_point)

    def delete(self, item_id):
        if self.get(item_id) is None:
            return False

        # Không trả bản mới sau delete.
        self.delta.pop(item_id, None)
        # Che bản cũ trong base, nếu base từng chứa ID ấy.
        if item_id in self.base:
            self.tombstones.add(item_id)
        self._maybe_rebuild()
        return True

    def current(self):
        """Snapshot logic của tất cả ID đang sống."""
        active = {
            item_id: p
            for item_id, p in self.base.items()
            if item_id not in self.tombstones
            and item_id not in self.delta
        }
        active.update(self.delta)
        return active

    def rebuild(self):
        """Dựng lại từ trạng thái logic mới, theo thứ tự tuần tự."""
        fresh = self.current()
        fresh_root = self._build(list(fresh.items()), depth=0)
        # Trong code tuần tự: không có update/truy vấn xen kẽ.
        self.base = fresh
        self.root = fresh_root
        self.delta.clear()
        self.tombstones.clear()
        self.rebuild_count += 1

    def range_ids(self, raw_lo, raw_hi):
        """Q là hình chữ nhật ĐÓNG theo từng trục."""
        qlo = _point(raw_lo)
        qhi = _point(raw_hi)
        if qlo[0] > qhi[0] or qlo[1] > qhi[1]:
            raise ValueError("Cận dưới Q không được vượt cận trên")

        hits = []

        def visit(node):
            if node is None:
                return
            if not _bbox_intersects_closed(
                node.lo, node.hi, qlo, qhi
            ):
                return

            # Phiên bản base không còn hiệu lực nếu delta ghi đè.
            if (node.id not in self.tombstones
                    and node.id not in self.delta
                    and _inside_closed(node.point, qlo, qhi)):
                hits.append(node.id)

            visit(node.left)
            visit(node.right)

        visit(self.root)

        # Delta có thể chứa điểm MỚI ở ngoài toàn bộ AABB base.
        for item_id, point in self.delta.items():
            if _inside_closed(point, qlo, qhi):
                hits.append(item_id)
        return sorted(hits)

    def nearest_id(self, raw_query):
        q = _point(raw_query)
        best = None  # (distance², ID); tie theo ID.

        # Kiểm tra delta trước để có upper bound tốt sớm.
        for item_id, point in self.delta.items():
            key = (_distance_sq(q, point), item_id)
            if best is None or key < best:
                best = key

        def visit(node):
            nonlocal best
            if node is None:
                return

            # Bbox base bao cả những ID đã chết, nhưng vẫn
            # bao mọi ID base còn sống: prune bảo thủ, an toàn.
            bound = _min_distance_sq(q, node.lo, node.hi)
            if best is not None and bound > best[0]:
                return

            if (node.id not in self.tombstones
                    and node.id not in self.delta):
                key = (_distance_sq(q, node.point), node.id)
                if best is None or key < best:
                    best = key

            children = [
                c for c in (node.left, node.right) if c is not None
            ]
            children.sort(
                key=lambda c: _min_distance_sq(q, c.lo, c.hi)
            )
            for child in children:
                visit(child)

        visit(self.root)
        return None if best is None else best[1]

    def stats(self):
        def height(node):
            if node is None:
                return 0
            return 1 + max(height(node.left), height(node.right))

        return {
            "base_records": len(self.base),
            "delta_records": len(self.delta),
            "tombstones": len(self.tombstones),
            "live_records": len(self.current()),
            "base_height": height(self.root),
            "rebuild_count": self.rebuild_count,
            "rebuild_threshold": self._threshold(),
        }

    def validate(self):
        """Kiểm tra base, overlay và AABB từ dữ liệu base."""
        seen = set()

        def walk(node, constraints):
            if node is None:
                return []

            if node.id in seen:
                raise AssertionError("Pivot ID bị nhân bản")
            seen.add(node.id)
            if self.base.get(node.id) != node.point:
                raise AssertionError("Điểm base khác nội dung node")

            for axis, pivot_key, is_left in constraints:
                current_key = (node.point[axis], node.id)
                if is_left and not current_key < pivot_key:
                    raise AssertionError("Sai ràng buộc nhánh trái")
                if not is_left and not current_key > pivot_key:
                    raise AssertionError("Sai ràng buộc nhánh phải")

            pivot_key = (node.point[node.axis], node.id)
            all_points = (
                [(node.id, node.point)]
                + walk(
                    node.left,
                    constraints + [(node.axis, pivot_key, True)],
                )
                + walk(
                    node.right,
                    constraints + [(node.axis, pivot_key, False)],
                )
            )
            lo = (
                min(p[0] for _, p in all_points),
                min(p[1] for _, p in all_points),
            )
            hi = (
                max(p[0] for _, p in all_points),
                max(p[1] for _, p in all_points),
            )
            if node.lo != lo or node.hi != hi:
                raise AssertionError("AABB base không khớp")
            if node.size != len(all_points):
                raise AssertionError("Subtree size base không khớp")
            return all_points

        walk(self.root, [])
        if seen != set(self.base):
            raise AssertionError("Pivot ID và base không trùng khớp")
        if not self.tombstones <= set(self.base):
            raise AssertionError("Tombstone không thuộc base")
        if self.tombstones & set(self.delta):
            raise AssertionError("Delta và tombstone có ID chung")
        return True
~~~

### Những quyết định quan trọng trong mã

**Median của base không thay đổi theo từng upsert:** Mọi điểm mới/di chuyển nằm trong delta, vì vậy split key và AABB của cây cơ sở không bị sửa sai.

**Delta che bản base:** Nếu ID A ở \((1,1)\) trong base và delta ghi A ở \((100,100)\), range quanh \((1,1)\) **không trả A**; range quanh \((100,100)\) **có trả A**.

**NN không dùng bản base stale:** Một điểm base đã bị ghi đè không được cập nhật best, vì khoảng cách của vị trí cũ không còn đại diện cho ID ấy. Cận AABB của base vẫn an toàn dù có thể lỏng.

**Tombstone riêng cho delete:** Nếu xóa ID đang được delta ghi đè và ID ấy cũng có trong base, mã đồng thời bỏ delta và đánh tombstone base. Nhờ vậy bản cũ không “hiện lại”.

**Rebuild từ current:** Hợp các ID base còn sống với delta, rồi xây median tree mới; chỉ sau khi dựng xong mới thay base và xóa pending. Đoạn mã tuần tự không tự tạo ra bảo đảm giao dịch khi có nhiều thread.

**Không thay một ID bằng cả hai phiên bản:** Range và NN chỉ trả **ID hiện hành**, không nhân đôi bản ghi.

**Giới hạn của ví dụ:** Tính khoảng cách bằng bình phương float. Tọa độ đầu vào hữu hạn không đủ bảo đảm các phép trừ/bình phương cực lớn không tràn; cần kiểm soát miền số trong ứng dụng yêu cầu chính xác số học chặt chẽ.

## 18. Python: kiểm thử overlay qua nhiều chu kỳ update và rebuild

Đoạn mã dưới đây **nối tiếp** lớp BufferedKDIndex ở mục 17. Các phép kiểm chứng dùng một **oracle dictionary** độc lập, không sử dụng AABB hay cây, nhằm phát hiện lỗi mất ID hoặc trả nhầm tọa độ cũ.

~~~python
base = [
    ("A", (0, 0)),
    ("B", (4, 0)),
    ("C", (0, 4)),
    ("D", (4, 4)),
    ("E", (2, 2)),
    ("F", (2, 2)),   # Trùng vị trí E, ID khác.
]
index = BufferedKDIndex(
    base, rebuild_fraction=0.25, min_pending=8
)

assert index.validate()
assert index.nearest_id((2, 2)) == "E"
assert index.range_ids((2, 2), (2, 2)) == ["E", "F"]

# Di chuyển E: bản base ở (2,2) phải bị che.
index.upsert("E", (10, 10))
assert index.get("E") == (10.0, 10.0)
assert index.range_ids((2, 2), (2, 2)) == ["F"]
assert index.range_ids((10, 10), (10, 10)) == ["E"]
assert index.nearest_id((2, 2)) == "F"

# Xóa F: base F là tombstone.
assert index.delete("F")
assert not index.delete("F")
assert index.range_ids((2, 2), (2, 2)) == []
assert index.nearest_id((2, 2)) == "A"

# Xóa E trong delta: phải che cả bản E cũ trong base.
assert index.delete("E")
assert index.get("E") is None
assert index.range_ids((2, 2), (2, 2)) == []

# Upsert lại E ở vị trí mới: nó thắng mọi bản cũ.
index.upsert("E", (8, 8))
assert index.get("E") == (8.0, 8.0)
assert index.range_ids((8, 8), (8, 8)) == ["E"]
assert index.range_ids((2, 2), (2, 2)) == []
assert index.validate()

# Đủ pending update -> tự rebuild; không được mất phiên bản mới.
before = index.stats()["rebuild_count"]
for j in range(12):
    index.upsert(f"N{j:02d}", (20 + j, 20))
    assert index.validate()
assert index.stats()["rebuild_count"] > before
assert index.get("E") == (8.0, 8.0)
assert index.get("F") is None
assert index.range_ids((20, 20), (31, 20)) == [
    f"N{j:02d}" for j in range(12)
]


def oracle_range(oracle, qlo, qhi):
    return sorted(
        item_id
        for item_id, p in oracle.items()
        if _inside_closed(p, qlo, qhi)
    )


def oracle_nn(oracle, q):
    if not oracle:
        return None
    return min(
        (_distance_sq(q, p), item_id)
        for item_id, p in oracle.items()
    )[1]


# Khởi tạo oracle từ trạng thái logic hiện hành.
oracle = index.current()
from random import Random
random = Random(2026)

# Thay đổi ID nhiều lần; cuối mỗi bước phải khớp brute-force.
for step in range(140):
    item_id = f"N{random.randrange(40):02d}"
    if random.randrange(5) == 0:
        actual = index.delete(item_id)
        expected = item_id in oracle
        assert actual == expected
        oracle.pop(item_id, None)
    else:
        point = (
            float(random.randrange(-10, 40)),
            float(random.randrange(-10, 40)),
        )
        index.upsert(item_id, point)
        oracle[item_id] = point

    assert index.validate()
    assert index.current() == oracle
    for query_lo, query_hi in [
        ((-10, -10), (0, 0)),
        ((0, 0), (10, 10)),
        ((20, 20), (30, 30)),
        ((-20, -20), (50, 50)),
    ]:
        assert index.range_ids(
            query_lo, query_hi
        ) == oracle_range(oracle, query_lo, query_hi)

    for query in [(0, 0), (8, 8), (25, 20), (100, 100)]:
        assert index.nearest_id(query) == oracle_nn(
            oracle, query
        )

# Rebuild thủ công cũng phải giữ đúng toàn bộ bản ghi.
before_compact = index.current()
index.rebuild()
assert index.validate()
assert index.current() == before_compact
assert index.stats()["delta_records"] == 0
assert index.stats()["tombstones"] == 0

# Tập rỗng và xóa ID chỉ tồn tại trong delta.
empty = BufferedKDIndex([])
empty.upsert("only-new", (1, 1))
assert empty.delete("only-new")
assert empty.current() == {}
assert empty.nearest_id((1, 1)) is None
assert empty.range_ids((0, 0), (2, 2)) == []
assert empty.validate()
~~~

### Các lỗi mà bộ test nhắm tới

**Move ID nhiều lần:** Sau khi E rời (2,2), truy vấn ở (2,2) không được trả E. Một ID chỉ có **một phiên bản hiện hành**.

**Xóa ID bị delta ghi đè:** Nếu bỏ delta nhưng không tombstone bản base, ID “sống lại” ở vị trí cũ. Test delete E được thiết kế để phát hiện lỗi này.

**Rebuild khi pending đủ lớn:** Quá trình compact phải tính dữ liệu logic mới **trước** khi xóa delta và tombstone.

**So với oracle:** Oracle dùng dict và quét toàn bộ, không dùng bất biến split/AABB, giúp kiểm tra **tính đúng** độc lập với cách tổ chức chỉ mục.

**Lưu ý STEP 4:** Đoạn Python và lệnh assert là ví dụ cho người đọc tự chạy. Trong tác vụ biên soạn này **không thực thi Python hoặc vòng QA chuyên môn**; các lệnh kiểm thử được viết ra không phải xác nhận đã chạy thành công.

## 19. Python: spatial hash cập nhật trực tiếp theo bucket

Đối với dữ liệu chuyển động nhanh, một **grid cố định** có thể không cần delta hay rebuild cây: chỉ cần chuyển ID giữa các ô khi tọa độ vượt biên. Ví dụ dưới đây cho thấy điều này, đồng thời lưu **ánh xạ ID → tọa độ hiện hành** để không mất dữ liệu khi update.

Mỗi ô có chiều rộng s, bắt đầu từ gốc \((o_x,o_y)\). ID của mọi bản ghi hiện hành xuất hiện trong **đúng một tập bucket**. Các ô rỗng có thể bị xóa khỏi hash map.

~~~python
from math import floor, isfinite


class MovingGrid:
    def __init__(self, cell_size=4.0, origin=(0.0, 0.0)):
        self.s = float(cell_size)
        self.origin = (float(origin[0]), float(origin[1]))
        if (not isfinite(self.s) or self.s <= 0
                or not all(isfinite(v) for v in self.origin)):
            raise ValueError("Cell size và origin phải hợp lệ")
        self.points = {}  # ID -> tọa độ đang sống.
        self.buckets = {} # (i,j) -> tập ID.

    def _cell(self, p):
        return (
            floor((p[0] - self.origin[0]) / self.s),
            floor((p[1] - self.origin[1]) / self.s),
        )

    def upsert(self, item_id, raw_point):
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("ID phải là chuỗi không rỗng")
        p = _point(raw_point)  # Dùng helper mục 17.

        if item_id in self.points:
            old_cell = self._cell(self.points[item_id])
            self.buckets[old_cell].remove(item_id)
            if not self.buckets[old_cell]:
                del self.buckets[old_cell]

        new_cell = self._cell(p)
        self.buckets.setdefault(new_cell, set()).add(item_id)
        self.points[item_id] = p

    def delete(self, item_id):
        if item_id not in self.points:
            return False
        old_cell = self._cell(self.points.pop(item_id))
        self.buckets[old_cell].remove(item_id)
        if not self.buckets[old_cell]:
            del self.buckets[old_cell]
        return True

    def range_ids(self, raw_lo, raw_hi):
        lo, hi = _point(raw_lo), _point(raw_hi)
        if lo[0] > hi[0] or lo[1] > hi[1]:
            raise ValueError("Q phải có cận dưới <= cận trên")

        i0, j0 = self._cell(lo)
        i1, j1 = self._cell(hi)
        hits = []
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                for item_id in self.buckets.get((i, j), ()):
                    p = self.points[item_id]
                    if _inside_closed(p, lo, hi):
                        hits.append(item_id)
        return sorted(hits)

    def occupancy(self):
        sizes = [len(ids) for ids in self.buckets.values()]
        return {
            "live_records": len(self.points),
            "occupied_cells": len(sizes),
            "max_bucket": max(sizes, default=0),
        }

    def validate(self):
        seen = set()
        for cell, ids in self.buckets.items():
            if not ids:
                raise AssertionError("Bucket rỗng chưa xóa")
            for item_id in ids:
                if item_id in seen:
                    raise AssertionError("ID ở nhiều bucket")
                if item_id not in self.points:
                    raise AssertionError("Bucket chứa ID đã xóa")
                if self._cell(self.points[item_id]) != cell:
                    raise AssertionError("ID ở bucket sai")
                seen.add(item_id)
        if seen != set(self.points):
            raise AssertionError("Thiếu ID trong bucket")
        return True
~~~

### Tính đúng và chi phí update

Trong **chế độ tuần tự** với hash table có thao tác trung bình \(O(1)\), mỗi upsert/delete chỉ cần tìm bucket cũ/mới và sửa tập ID, nên thường gần \(O(1)\) **trung bình**, chưa kể chi phí hash/key và bộ nhớ. Đây không phải bảo đảm worst-case: hash collision, rehash, cấp phát và nhiều thread có thể khiến chi phí lớn hơn.

Range query phải **liệt kê mọi ô có thể chứa điểm thuộc Q** và kiểm tra các ứng viên ở đó. Nếu Q rất rộng và ô s quá nhỏ, việc liệt kê quá nhiều ô có thể tốn thời gian ngay cả khi các ô ấy **không tồn tại trong hash map**.

Vì vậy MovingGrid là ví dụ về cách **update đơn giản**, không phải bằng chứng grid luôn nhanh hơn BufferedKDIndex.

## 20. Python: kiểm chứng cập nhật grid, bucket nóng và query biên

Đoạn sau **nối tiếp** MovingGrid và helper từ mục 17. Mọi điểm có ID riêng dù tọa độ trùng, và cửa sổ truy vấn là **hộp đóng**.

~~~python
grid = MovingGrid(cell_size=4.0)

grid.upsert("A", (3.9, 2))
grid.upsert("B", (4.0, 2))
grid.upsert("C", (-0.1, 2))
assert grid.validate()
assert grid._cell((3.9, 2)) == (0, 0)
assert grid._cell((4.0, 2)) == (1, 0)
assert grid._cell((-0.1, 2)) == (-1, 0)

# Q đóng đến x=4: điểm đúng biên vẫn là kết quả.
assert grid.range_ids((0, 2), (4, 2)) == ["A", "B"]

# A băng qua đường chia và trùng vị trí B.
grid.upsert("A", (4, 2))
assert grid.range_ids((4, 2), (4, 2)) == ["A", "B"]
assert grid.occupancy()["max_bucket"] == 2
assert grid.validate()

# Di chuyển B thêm lần nữa; không được thấy bản cũ.
grid.upsert("B", (8, 2))
assert grid.range_ids((4, 2), (4, 2)) == ["A"]
assert grid.range_ids((8, 2), (8, 2)) == ["B"]
assert grid.validate()

# Xóa phải giải phóng đúng bucket cũ.
assert grid.delete("A")
assert not grid.delete("A")
assert grid.range_ids((4, 2), (4, 2)) == []
assert grid.validate()

# Tập rất lệch: 100 ID cùng một ô; occupancy đo rõ vấn đề.
hot = MovingGrid(cell_size=4)
for i in range(100):
    hot.upsert(f"id-{i:03d}", (1, 1))
assert hot.validate()
assert hot.occupancy() == {
    "live_records": 100,
    "occupied_cells": 1,
    "max_bucket": 100,
}
assert len(hot.range_ids((1, 1), (1, 1))) == 100

# Cùng dữ liệu hiện hành, so kết quả grid với brute force.
from random import Random

oracle = {
    f"id-{i:03d}": (1.0, 1.0)
    for i in range(100)
}
random = Random(42)
for step in range(120):
    item_id = f"r{random.randrange(30):02d}"
    if random.randrange(4) == 0:
        removed = hot.delete(item_id)
        assert removed == (item_id in oracle)
        oracle.pop(item_id, None)
    else:
        p = (
            float(random.randrange(-8, 24)),
            float(random.randrange(-8, 24)),
        )
        hot.upsert(item_id, p)
        oracle[item_id] = p

    assert hot.validate()
    assert hot.points == oracle
    expected = sorted(
        item_id for item_id, p in oracle.items()
        if 0 <= p[0] <= 8 and 0 <= p[1] <= 8
    )
    assert hot.range_ids((0, 0), (8, 8)) == expected

# Bucket vẫn chứa cả 100 ID ban đầu ở (1,1).
assert hot.occupancy()["max_bucket"] >= 100
~~~

### Đọc đúng phạm vi bài kiểm chứng

Test ô nóng xác nhận hệ thống **không làm mất ID** khi 100 điểm cùng tọa độ và số liệu **max_bucket** phản ánh occupancy lệch.

Test chuyển qua x=4 xác nhận việc đưa ID vào ô mới và loại khỏi ô cũ. Nếu chỉ cập nhật tọa độ mà không sửa bucket, một range query ở vị trí mới có thể bỏ sót.

Trong vòng random phía trên, oracle được khởi tạo với **cả 100 ID ban đầu** và cập nhật theo các thao tác mới. Việc so kết quả query với oracle là **quét tham chiếu độc lập** với cách lập bucket; điều kiện **hot.points == oracle** còn giúp phát hiện cập nhật sai tọa độ hoặc bỏ sót ID.

**Lưu ý:** Đây là ví dụ để người học chạy; nhiệm vụ biên soạn STEP 4 **không thực thi Python**. Các assert được trình bày nhằm diễn đạt điều kiện đúng cần kiểm tra, không phải báo cáo một lần chạy kiểm thử thực tế.

## 21. Đo hiệu năng: đừng chỉ nhìn thời gian trung bình

Để tìm nguyên nhân suy giảm, hãy ghi nhận **cùng lúc** dữ liệu, cấu trúc, truy vấn và thay đổi theo thời gian.

### Nhóm chỉ số về dữ liệu và cấu trúc

| Nhóm | Chỉ số hữu ích |
| --- | --- |
| Dữ liệu | \(n\), số tọa độ phân biệt, số ID trùng tọa độ, phạm vi min/max |
| Mật độ | Heatmap/histogram theo ô, max/p95 occupancy, điểm/đơn vị diện tích |
| K-d tree | Height, độ sâu p95, node thăm/query, AABB diện tích/tỷ lệ node bị prune |
| Quadtree | Max depth, số node một con, bucket quá capacity do trùng tọa độ |
| Grid | Cell size, số bucket không rỗng, max/p95 bucket size, số ô liệt kê |
| R-tree | MBR overlap/coverage, tỷ lệ lấp đầy page, branch forks và page reads |
| Delta index | \(|B|,|\Delta|,|T|\), số rebuild, thời gian rebuild, tỷ lệ ID chết |
| Khai thác | Query hotspot, tỷ lệ read/write, tỷ lệ move qua cell boundary |

### Nhóm chỉ số theo truy vấn

Đừng chỉ đo \(p50\) hoặc trung bình của toàn bộ Q. Nên tách:

- Query ở vùng **dày** và vùng **thưa**.
- Query có **kết quả rỗng**, có vài ID và có hàng trăm nghìn ID.
- Query **điểm**, cửa sổ nhỏ, cửa sổ dài/mảnh, bán kính lớn.
- Query NN ở gần một cụm, **giữa các cụm**, hoặc rất xa dữ liệu.
- Query theo các khoảng thời gian **trước/sau cao điểm cập nhật**.

Khi p99 tăng, cần tìm xem đó là do **số kết quả k**, **số node thăm V**, **chi phí quét delta**, **thời gian chờ khóa** hay **cache miss/I/O**.

### So sánh trước và sau rebuild

Một benchmark có tính giải thích nên ghi:

| Chỉ số | Trước rebuild | Sau rebuild | Diễn giải |
| --- | --- | --- | --- |
| Số ID hiện hành | Không đổi | Không đổi | Rebuild không làm thay tập dữ liệu |
| Delta/tombstone | Có thể nhiều | 0 ngay sau compact | Giảm lớp pending |
| Chiều cao base k-d tree | Có thể giữ nguyên nếu base tĩnh | Median tree cân bằng | Không khẳng định mọi query nhanh hơn |
| Số node được thăm | Cần đo | Cần đo | Có thể giảm do AABB chặt hơn |
| Query kết quả k | Phải giống nhau | Phải giống nhau | Điều kiện correctness |
| Thời gian build | 0 khi query | Có chi phí một lần | Phải khấu hao theo workload |

Nếu sau rebuild \(V\) không giảm và p99 không đổi, có thể vấn đề nằm ở **phân bố hình học**, **khối lượng đầu ra**, **metric**, hoặc **truy vấn quá rộng**, chứ không ở tombstone/overlay.

### Thước đo tốc độ có tính công bằng

Nếu chỉ báo cáo “số node thăm giảm 80%” nhưng bỏ qua rằng mỗi node của chỉ mục mới đắt gấp 10 lần do heap/metadata, kết luận có thể sai. Nên đo **độ trễ thực tế** và các counter giải thích, cùng mức sử dụng RAM/CPU/I/O.

Một cách đánh giá tổng hợp:

\[
\boxed{
\operatorname{speedup}=
\frac{T_{\mathrm{baseline}}}
{T_{\mathrm{index}}}
}
\]

với **cùng tập dữ liệu, cùng truy vấn, cùng predicate và cùng điều kiện máy chạy**. Nếu có khác biệt kết quả, không được dùng speedup đó để chứng minh thuật toán tốt hơn.

## 22. Bảng chi phí và giới hạn cho chỉ mục động

Ký hiệu:

- \(n\): số điểm trong base, \(u\): số ID delta, \(t\): tombstones.
- \(V_B\): số node base k-d tree thăm thật sự.
- \(h\): chiều cao base, \(k\): số ID kết quả.
- \(b\): số bucket grid không rỗng, \(c\): số ô grid được liệt kê.
- \(m_Q\): số ID trong bucket được xét cho Q.
- \(M\): sức chứa node R-tree, \(S\): số node split của một lần chèn.

| Phép toán | Chi phí điển hình hoặc cận theo lượng việc |
| --- | --- |
| Quét tuyến tính range/NN 2D | \(O(n)\) |
| K-d tree median build bằng sort ở mỗi node | \(O(n\log^2n)\) trong 2D |
| 1-NN trên base k-d tree | \(O(V_B)\) trong 2D, worst-case \(O(n)\) |
| Range trên base+delta | \(O(V_B+u+k\log k)\) khi sắp k ID đầu ra |
| 1-NN trên base+delta | \(O(V_B+u)\) trong 2D |
| Upsert/delete trong overlay | \(O(1)\) trung bình **khi chưa rebuild**, với dict/set hash |
| Rebuild base từ \(n+u\) ID hiện hành | \(O(N\log^2N)\), \(N=|\mathcal D|\), theo cách xây minh họa |
| Spatial hash upsert/delete | \(O(1)\) trung bình, không bao gồm rehash/chi phí bất thường |
| Spatial hash range | \(O(c+m_Q+k\log k)\) nếu sắp ID |
| PR-quadtree range | \(O(V+m_Q+k)\) nếu \(V\) node được xét, \(m_Q\) điểm thực kiểm tra trong bucket; \(V\) có thể vượt n khi tồn tại chuỗi node đơn nhánh dài |
| R-tree ChooseSubtree và chèn | Khoảng \(O(Mh+SM^2)\) nếu split quadratic, \(S\le h\) |
| R-tree range | \(O(V+E_V+k)\) nếu object là rectangle và không sắp đầu ra |

**Giải thích:** Với k-d tree base+delta, \(V_B\) ở đây bao gồm các node xét trong traversal; cận worst-case có thể đạt toàn bộ base. Với grid, \(m_Q\) là số điểm phải xét trong những bucket được liệt kê, kể cả điểm **không** nằm trong Q. Những công thức không tính I/O/concurrency trừ khi được ghi rõ.

### Tại sao không gán một Big-O đẹp cho mọi tình huống?

Một chỉ mục có thể thăm gần n bản ghi vì:

- Q chứa rất nhiều điểm.
- Cận MBR/AABB quá lỏng.
- Nhiều hộp R-tree cùng giao Q.
- Bucket grid quá đông.
- Quadtree phải đi sâu qua nhiều ô đơn nhánh.
- Exact NN trong nhiều chiều phải thăm nhiều vùng.

Vì thế một phát biểu “chỉ mục không gian truy vấn \(O(\log n)\)” không có giả thiết cụ thể là **không đáng tin**. Với range reporting, riêng việc xuất k kết quả đã cần:

\[
\boxed{\Omega(k).}
\]

## 23. Những sai lầm thường gặp khi chỉ mục suy giảm

1. **“Dữ liệu tập trung tự động làm k-d tree median vừa xây có chiều cao tuyến tính.”** Sai. Median dựng tĩnh cân bằng số ID; skew có thể ảnh hưởng **hình học/cận prune**, không tự làm lệch chiều cao.
2. **“Sau khi chèn động vào median k-d tree, mọi node vẫn là trung vị.”** Sai nếu chỉ giữ pivot cũ và chèn theo split key.
3. **“Cây cân theo số node thì exact NN luôn \(O(\log n)\).”** Sai. NN có thể phải xét nhiều nhánh vì cận khoảng cách kém chọn lọc.
4. **“Quadtree chia thành bốn ô thì số điểm bốn ô gần bằng nhau.”** Sai. Có thể toàn bộ điểm vào một ô.
5. **“Nếu nhiều điểm trùng tọa độ, chỉ cần chia quadtree mãi.”** Sai. Chia hình học không làm những ID cùng vị trí tách nhau; cần maxDepth/bucket ngoại lệ.
6. **“Các node quadtree một con luôn là lỗi tính đúng.”** Không. Chúng có thể hợp lệ nhưng tốn chiều sâu/bộ nhớ; compression có thể giúp.
7. **“Grid có thời gian tra hash O(1) nên range query O(1).”** Sai. Còn phải liệt kê ô và kiểm tra các bản ghi trong bucket.
8. **“Bucket occupancy trung bình 100 nghĩa là không bucket nào lớn.”** Sai. Một bucket nóng có thể chứa hàng trăm nghìn ID.
9. **“Tăng độ mịn của grid luôn cải thiện query.”** Sai. Một Q rộng có thể phải duyệt quá nhiều ô.
10. **“Tăng kích thước ô luôn giảm CPU.”** Sai. Bucket đông làm lọc điểm tốn kém.
11. **“Spatial hash có thể đặt tọa độ âm vào ô bằng ép integer cắt về 0.”** Sai ở các ngôn ngữ có truncation; cần floor phù hợp.
12. **“Điểm di chuyển trong grid chỉ cần thay tọa độ trong record.”** Sai khi nó vượt ranh giới ô; phải chuyển ID sang bucket mới.
13. **“R-tree không thể có MBR anh em chồng lấn.”** Sai. Overlap là nguyên nhân phải mở nhiều nhánh.
14. **“Hai child-MBR overlap nghĩa là object-ID bị nhân bản.”** Sai. Nhóm ID rời nhau vẫn có vùng bao giao nhau.
15. **“MBR rộng là lỗi tính đúng.”** Không, nếu vẫn bao toàn bộ dữ liệu; nó chỉ làm prune kém.
16. **“MBR hẹp thiếu một object chỉ khiến query chậm hơn.”** Sai nguy hiểm. Nó có thể làm **false negative**.
17. **“Một object rất lớn có thể luôn được nhóm sao cho MBR cha nhỏ.”** Không. MBR cha phải bao object đó; giới hạn hình học là bắt buộc.
18. **“Sau split R-tree không cần cập nhật entry cha.”** Sai. Cha có thể phải nhận sibling mới và cập nhật MBR, đôi khi split tiếp.
19. **“R\*-tree hoặc STR luôn thắng R-tree trên mọi dữ liệu.”** Không có bảo đảm tổng quát. Cần đo build/update/query thực tế.
20. **“Truy vấn trả k=0 luôn nhanh.”** Sai. Nhiều AABB/MBR có thể giao Q nhưng không chứa điểm/hình thật được Q nhận.
21. **“p50 tốt chứng minh không có đuôi độ trễ.”** Sai. Phải đo p95/p99 và tách hotspot.
22. **“Skew dữ liệu và skew truy vấn là cùng một đại lượng.”** Sai. Một vùng dày có thể ít được hỏi, và một vùng thưa có thể là hotspot.
23. **“Rebuild khắc phục mọi query chậm.”** Sai. Rebuild không giảm số ID phải xuất nếu Q thật sự chứa rất nhiều điểm.
24. **“Có thể rebuild ngay sau mỗi update mà không có chi phí.”** Sai. Chi phí CPU/I/O, RAM và độ trễ update có thể rất lớn.
25. **“Chỉ cần dùng tombstone thì xóa một ID hoàn toàn khỏi chi phí truy vấn.”** Sai. Entry vật lý và AABB cũ có thể vẫn làm query đi qua vùng dư.
26. **“Tombstone có thể bị bỏ qua khi range counting dùng subtree size.”** Sai. Size chưa điều chỉnh sẽ đếm cả ID đã xóa.
27. **“Xóa một ID trong delta đủ để xóa nó nếu nó còn ở base.”** Sai. Nếu không tombstone base, bản cũ sẽ **sống lại**.
28. **“Upsert có thể giữ cả bản base cũ và delta mới trong kết quả.”** Sai. Mỗi ID logic có một phiên bản hiện hành.
29. **“NN chỉ cần loại bản base cũ lúc trả kết quả, vẫn có thể cho nó cập nhật best tạm thời.”** Sai. Best stale quá tốt có thể làm prune sai nhánh chứa nghiệm hiện hành.
30. **“Truy vấn base trước, nếu không thấy gì mới xem delta cũng luôn chính xác.”** Với NN, phải so tất cả ứng viên hợp lệ ở cả hai tầng; với range, phải hợp kết quả hai tầng. Dừng trước khi xét delta có thể bỏ điểm mới.
31. **“AABB base có tombstone không còn an toàn cho prune.”** Nó vẫn an toàn **nếu còn bao mọi bản base còn sống**; chỉ có thể quá rộng.
32. **“Rebuild xóa delta trước rồi mới xây cây cũng được.”** Sai. Nếu thất bại giữa chừng có thể mất update. Cần tạo trạng thái mới trước khi bỏ dữ liệu đang phục vụ.
33. **“Snapshot lúc bắt đầu build là đủ, update mới trong lúc build không cần replay.”** Sai. Có nguy cơ mất các update sau snapshot khi chuyển thế hệ.
34. **“Đọc nửa chỉ mục cũ và nửa delta mới lúc bất kỳ đều là một snapshot hợp lệ.”** Sai nếu hệ thống cần nhất quán giữa các bản ghi/phiên bản.
35. **“Chỉ mục càng ít node thăm càng đúng.”** Sai. Số node ít bất thường có thể do bbox lỗi khiến bỏ sót kết quả.
36. **“Tọa độ đầu vào float hữu hạn bảo đảm mọi phép tính bình phương hữu hạn.”** Sai. Hiệu cực lớn có thể tràn hoặc mất độ chính xác.
37. **“Euclid trên kinh độ/vĩ độ theo độ tự cho NN theo mét.”** Sai. Phải xác định metric/hệ quy chiếu.
38. **“Hai điểm cùng tọa độ nên chỉ trả một ID trong radius=0.”** Sai nếu chúng là hai bản ghi có ID khác nhau.
39. **“Khi minDist² bằng best² có thể bỏ nhánh dù tie ưu tiên ID nhỏ hơn.”** Sai. Nhánh có thể chứa điểm cùng khoảng cách nhưng ID tốt hơn.
40. **“Một benchmark chỉ đo thời gian truy vấn mà không đo build/update là đủ để chọn chỉ mục động.”** Sai. Tổng chi phí có thể bị chi phối bởi bảo trì.
41. **“Chuyển dữ liệu sang ANN là tối ưu trong mọi bài toán.”** Sai nếu yêu cầu kết quả exact; cần nêu rõ bảo đảm hoặc recall.
42. **“Hysteresis split/merge cho phép để điểm ở sai ô.”** Sai. Nó chỉ quyết định khi chia/gộp, không cho phép phá quy tắc sở hữu miền.
43. **“Rebuild càng thường xuyên thì p99 càng nhỏ.”** Không luôn đúng: chính rebuild có thể tạo spike tài nguyên/độ trễ.
44. **“Tổng số object tăng ít nghĩa là chỉ số không bị suy giảm.”** Sai. Nhiều move và thay đổi vị trí có thể làm cấu trúc cũ kém chọn lọc dù n gần như không đổi.

## 24. Checklist xử lý chỉ mục đang suy giảm trong production

Khi hệ thống xuất hiện “độ trễ tăng theo thời gian”, không nên ngay lập tức đổi cấu trúc. Một quy trình điều tra có thể đi theo thứ tự:

### Bước 1 — Bảo đảm kết quả đúng

Lấy mẫu truy vấn Q và snapshot dữ liệu ở **cùng phiên bản**, tính kết quả bằng quét tuyến tính. So:

\[
\boxed{
\operatorname{IDs}_{\mathrm{index}}(Q)
=\operatorname{IDs}_{\mathrm{brute}}(Q).
}
\]

Với NN, so cặp \((distance^2,ID)\), không chỉ khoảng cách; với radius, xác định rõ biên **\(\le r\)**. Nếu có sai kết quả, dừng tối ưu hiệu năng và sửa invariant/version.

### Bước 2 — Xác định điểm nghẽn

Thu thập cùng thời điểm: chiều cao, node visits, bucket occupancy, MBR overlap, delta/tombstone, số ID trả ra k, CPU, I/O, lock wait. Chia theo khu vực và loại truy vấn thay vì chỉ báo trung bình toàn hệ thống.

### Bước 3 — Chọn giả thuyết cụ thể

Ví dụ:

- **Giả thuyết A:** k-d tree base có 40% tombstone khiến AABB rộng, rebuild giảm node visits.
- **Giả thuyết B:** một bucket grid chứa 100.000 điểm khiến Q quanh hotspot chậm.
- **Giả thuyết C:** R-tree có nhiều MBR sibling overlap nên một Q mở hơn 30 nhánh.
- **Giả thuyết D:** Q trả 500.000 ID nên dù rebuild vẫn bị giới hạn bởi xuất dữ liệu.

Mỗi giả thuyết phải có **thước đo xác nhận/bác bỏ**, không chỉ mô tả chung “dữ liệu lớn”.

### Bước 4 — Thử can thiệp trên cùng snapshot

Trên một bản dữ liệu giống nhau, so baseline hiện tại với:

- Rebuild base/compact delta.
- Đổi cell size hoặc thêm cấp chia bucket nóng.
- Quadtree compression/bucket policy.
- R-tree bulk loading/R\*-tree hoặc thay chiến lược split.
- Quét tuyến tính/vector hóa khi n thấp hay Q rất rộng.

Chạy cùng bộ Q đại diện, so **kết quả trước** rồi so **độ trễ và tài nguyên**.

### Bước 5 — Triển khai an toàn

Nếu rebuild chạy đồng thời, dùng snapshot/version và generation swap. Xác nhận mọi update đã được replay và thiết lập cách rollback nếu chỉ mục mới không khớp dữ liệu logic.

### Bước 6 — Tiếp tục theo dõi

Theo dõi p50/p95/p99, tỷ lệ rebuild, bộ nhớ đỉnh, update latency, tỷ lệ lỗi và độ chính xác query sau khi triển khai. Một phương án tốt ở phân bố buổi sáng có thể suy giảm khi hotspot đổi sang khu khác buổi tối.

### Mẫu quyết định ngắn

~~~text
Query sai?
    Có -> kiểm tra ID/version/MBR/bucket/split key, sửa correctness.
    Không ->
        Đầu ra k lớn?
            Có -> xem giới hạn xuất dữ liệu, batching/pagination.
            Không ->
                Delta/tombstone lớn? -> thử compaction/rebuild.
                Bucket quá đông? -> thử đổi grid/bucket/hybrid.
                Cây quá sâu? -> thử balance/compress/rebuild.
                MBR overlap rộng? -> thử R*-tree/STR/reinsert.
                Không rõ? -> đo lại workload, CPU, cache, I/O.
~~~

## 25. Bài tập tự kiểm tra kèm lời giải

### Câu 1. K-d tree tĩnh và skew

Một tập có 1.023 điểm, trong đó 1.000 điểm nằm trong một vùng rất nhỏ. Nếu xây k-d tree bằng trung vị theo số ID ở từng node, có bắt buộc chiều cao tăng tới \(\Theta(n)\) vì dữ liệu tập trung không?

**Lời giải:** **Không.** Trung vị chia số phần tử hai bên gần bằng nhau, nên chiều cao của cây tĩnh vẫn \(O(\log n)\) nếu thuật toán median split đúng. Skew có thể làm hình dạng cell/AABB và khả năng prune bất lợi, nhưng không tự phá cân bằng số ID.

### Câu 2. Chèn vào cây cũ

Một k-d tree được dựng cân bằng từ 100 điểm. Sau đó chèn 10.000 điểm mới theo một chuỗi bất lợi mà không rebuild. Có bảo đảm chiều cao vẫn \(O(\log n)\) không?

**Lời giải:** **Không.** Pivot cũ không tự cập nhật theo median. Nếu chính sách chèn không có cơ chế cân bằng, một số nhánh có thể kéo dài tới \(\Theta(n)\) trong trường hợp xấu.

### Câu 3. Quadtree có điểm cùng tọa độ

Bucket capacity=1, có 500 ID ở cùng vị trí (3,3). Nếu mỗi lần đầy chỉ chia vùng thành bốn, khi nào dừng được?

**Lời giải:** Không thể tách những ID cùng tọa độ chỉ bằng chia hình học. Cần **maxDepth, giới hạn độ phân giải** hoặc giữ một bucket đặc biệt chứa nhiều ID. Nếu không có điều kiện dừng, thao tác có thể không kết thúc.

### Câu 4. Grid occupancy trung bình có thể che hotspot

Có 1.000.000 điểm trong 10.000 bucket không rỗng. Bucket đông nhất có 300.000 điểm. Trung bình và tỷ lệ lớn nhất/trung bình bằng bao nhiêu?

**Lời giải:** Trung bình \(1\,000\,000/10\,000=100\) điểm/bucket. Tỷ lệ \(300\,000/100=\boxed{3\,000}\). Chỉ báo cáo trung bình 100 sẽ che giấu bucket cực nóng.

### Câu 5. Ô có tọa độ âm

Spatial hash với \(s=4\), gốc (0,0). Điểm \((-0.1,5)\) có chỉ số ô nào?

**Lời giải:** \(i=\lfloor-0.1/4\rfloor=-1\), \(j=\lfloor5/4\rfloor=1\), nên ô **(-1,1)**. Phải dùng floor thay vì cắt số thập phân về 0.

### Câu 6. Di chuyển qua ranh giới

Điểm A di chuyển từ (3.9,2) sang (4,2) với cell size 4, gốc (0,0). Nếu chỉ thay tọa độ mà không chuyển bucket, lỗi gì xảy ra?

**Lời giải:** A phải chuyển từ ô **(0,0)** sang **(1,0)**. Giữ ở ô cũ làm range query tại x=4 có nguy cơ không duyệt ô cũ và **bỏ sót A**.

### Câu 7. R-tree và sibling overlap

Hai child-MBR của root là \([0,6]\times[0,6]\) và \([4,10]\times[4,10]\). Query Q=\([5,5]\times[5,5]\) có phải duyệt cả hai nhánh không?

**Lời giải:** **Có.** Q giao cả hai MBR. Chỉ chọn một nhánh có thể bỏ kết quả thật thuộc nhánh còn lại.

### Câu 8. Hình rất lớn

Một object có MBR \([0,1000]\times[0,1000]\). Có thể dùng thuật toán split để buộc MBR của nhóm chứa object đó chỉ nằm trong \([0,10]\times[0,10]\) không?

**Lời giải:** **Không.** MBR của nhóm phải bao toàn bộ object. Split có thể quyết định **nhóm nào chứa object**, nhưng không được làm hộp bao thiếu dữ liệu.

### Câu 9. MBR rộng có thể đúng không?

Node có MBR \([0,100]\times[0,100]\), nhưng mọi điểm còn sống chỉ thuộc \([0,10]\times[0,10]\). Query dựa trên MBR cũ có thể vẫn chính xác không?

**Lời giải:** **Có.** Hộp cũ bao tất cả dữ liệu còn sống nên prune khi hộp cũ không giao Q vẫn an toàn. Nó chỉ làm tăng nguy cơ **thăm nhánh dư**. Rebuild có thể thu hẹp hộp.

### Câu 10. MBR quá nhỏ

Một điểm đang ở (20,20) nhưng MBR tổ tiên vẫn \([0,4]\times[0,4]\). Query nhỏ quanh (20,20) có nguy cơ gì?

**Lời giải:** Query có thể thấy MBR cha không giao Q rồi bỏ cả nhánh, **trả thiếu điểm thật**. Đây là lỗi tính đúng do metadata không bao dữ liệu.

### Câu 11. Tombstone và counting

Một cây con có metadata size=500, nhưng 200 ID trong đó đã bị xóa theo tombstone. Q chứa trọn bbox node. Có thể cộng 500 để trả số bản ghi hiện hành không?

**Lời giải:** **Không.** Nếu không có ID mới ghi đè khác, chỉ còn 300 bản ghi sống trong cây con. Cần size sống đúng, hoặc bù trừ deleted/overwritten ID theo snapshot; không được dùng size vật lý 500.

### Câu 12. Upsert che phiên bản base

Base có A ở (1,1); delta có A ở (100,100). Với range Q chỉ chứa (1,1), có được trả A từ base không?

**Lời giải:** **Không.** Phiên bản delta là vị trí mới nhất của cùng ID A. Range quanh (100,100) mới được trả A.

### Câu 13. Xóa sau khi move

Base có B ở (2,2). Delta chuyển B sang (7,7). Sau đó Delete(B), nếu chỉ xóa delta mà không thêm tombstone, điều gì xảy ra?

**Lời giải:** Bản B trong base **xuất hiện lại** ở (2,2), dù Delete đã thành công. Phải **tombstone B trong base** cùng với việc bỏ phiên bản delta.

### Câu 14. Best stale trong NN

Base có A ở đúng q, delta chuyển A đi rất xa. Nếu thuật toán NN vẫn dùng bản A cũ ở q để đặt \(best^2=0\), nó có thể prune nhánh chứa NN hiện hành không?

**Lời giải:** **Có.** Best từ vị trí cũ không phải ứng viên hợp lệ. Nếu dùng nó làm ngưỡng, nhánh với cận dương có thể bị loại dù chứa điểm gần nhất còn sống. Chỉ dùng bản ghi **hiện hành** để cập nhật best.

### Câu 15. Cận AABB sau tombstone

Base AABB \([0,100]\times[0,100]\) còn vài điểm sống quanh (0,0); tombstone che mọi outlier. MinDist tới AABB base còn là cận dưới an toàn không?

**Lời giải:** **Có**, vì AABB base vẫn bao mọi điểm base còn sống. Nó có thể **lỏng hơn** cận chặt từ điểm sống, làm query thăm dư.

### Câu 16. Khi nào rebuild theo ngưỡng?

Base có 1.000 ID, \(\alpha=0.25\), \(u_{\min}=8\). Theo chính sách \(|\Delta|+|T|\ge\max(u_{\min},\lceil\alpha n_B\rceil)\), ngưỡng là bao nhiêu?

**Lời giải:**

\[
\boxed{\max(8,\lceil0.25\cdot1000\rceil)=250.}
\]

Khi tổng pending từ 250 trở lên, có thể trigger rebuild theo chính sách này.

### Câu 17. Cập nhật một ID rất nhiều lần

Một ID di chuyển 10.000 lần nhưng delta chỉ giữ tọa độ **mới nhất**. \(|\Delta|\) có nhất thiết tăng lên 10.000 không?

**Lời giải:** **Không.** Nếu chỉ ID ấy bị thay đổi, delta có thể vẫn chỉ có **một entry**. Ngưỡng theo số ID đang pending không phản ánh toàn bộ số lệnh update; việc này có thể hợp lý nếu query vẫn nhanh.

### Câu 18. Khấu hao rebuild

Giả sử rebuild tốn \(O(n\log^2n)\) và xảy ra sau mỗi \(\alpha n\) cập nhật khi n gần ổn định. Chi phí rebuild khấu hao trên một update là bao nhiêu?

**Lời giải:**

\[
\boxed{O(\log^2n/\alpha).}
\]

Đây là ước lượng có giả thiết; chưa bao gồm chi phí duyệt delta hay tranh chấp tài nguyên lúc rebuild.

### Câu 19. Dữ liệu đổi trong lúc build

Builder chụp snapshot lúc version 100; trong khi xây, ID C đổi vị trí ở version 101. Sau build, hệ thống swap sang cây mới nhưng xóa mọi delta mà không replay. Lỗi gì xảy ra?

**Lời giải:** Update version 101 có thể **bị mất**, khiến C quay về vị trí ở snapshot version 100. Cần replay delta/update log sau snapshot hoặc cơ chế version/swap an toàn tương đương.

### Câu 20. Query kết quả nhiều

Một range query trả đúng 300.000 ID. Sau rebuild, có thể đảm bảo thời gian xuất toàn bộ ID chỉ còn \(O(\log n)\) không?

**Lời giải:** **Không.** Chỉ riêng việc xuất 300.000 ID đã cần \(\Omega(300\,000)\). Rebuild có thể giảm node thăm dư, không loại bỏ giới hạn đầu ra.

### Câu 21. p99 và hotspot

Độ trễ trung bình toàn hệ thống tốt nhưng p99 rất cao. Phải kiểm tra những yếu tố nào trước khi đổi chỉ mục?

**Lời giải:** Phân tách query theo **vùng nóng, số kết quả k, node visits, bucket occupancy, delta/tombstone, CPU/I/O và lock wait**. Có thể p99 là do một nhóm query trả nhiều ID hoặc tranh chấp khóa, không phải do mọi cấu trúc bị lệch.

### Câu 22. Chọn cấu trúc cho chuyển động nhanh

500.000 vật thể nhỏ di chuyển liên tục, truy vấn chủ yếu tìm vật thể trong bán kính tương đối cố định ở 2D. Chọn hướng đáng thử nào?

**Lời giải:** Thử **uniform grid/spatial hash** với cell size hợp lý, cập nhật bucket khi vật thể qua ranh giới. Nếu mật độ quá lệch, thử quadtree động hoặc bucket thích nghi; benchmark đầy đủ update/query trước khi chọn.

### Câu 23. Có nên dùng ANN?

Hệ thống tìm hàng xóm của vector 256 chiều; exact NN rất chậm, nghiệp vụ chấp nhận kết quả gần đúng. Có thể thử ANN không? Cần công bố điều gì?

**Lời giải:** **Có thể thử** một chỉ mục ANN phù hợp, nhưng phải công bố **metric, mức độ chính xác/recall hoặc bảo đảm xấp xỉ** và đo latency. Không được gọi kết quả gần đúng là exact NN.

### Câu 24. Phân loại ba tình huống

(a) MBR cha sai nên query bỏ sót object; (b) MBR cha rộng nhưng bao đúng, query nhiều nhánh; (c) query trả một triệu kết quả hợp lệ. Mỗi tình huống nên ưu tiên xử lý gì?

**Lời giải:** (a) **Sửa correctness/bất biến ngay**, không benchmark sai; (b) **thử rebuild/reinsert/tối ưu grouping** và đo node visits; (c) **xem giới hạn xuất kết quả**, batching/pagination hoặc thay yêu cầu sản phẩm, không kỳ vọng rebuild loại bỏ chi phí \(\Omega(k)\).

## 26. Tổng kết

**Dữ liệu lệch** có thể là cụm tập trung, ID trùng tọa độ, outlier, object lớn, hotspot truy vấn hoặc cập nhật dồn vào một khu vực. Những hiện tượng ấy tác động khác nhau lên từng chỉ mục:

- **K-d tree median tĩnh** vẫn cân bằng số điểm khi build, nhưng AABB/cell có thể kém chọn lọc; chèn động không cân bằng có thể làm cây lệch và cần rebuild.
- **PR-quadtree** có thể tạo nhiều node đơn nhánh trong vùng dày; điểm trùng tọa độ đòi bucket đặc biệt, compression hoặc giới hạn độ sâu.
- **Spatial hash/grid** dễ cập nhật điểm khi đổi ô nhưng nhạy với cell size và phân bố **bucket occupancy**.
- **R-tree** có thể phải mở nhiều nhánh do MBR overlap, object kích thước lớn và thứ tự chèn; cập nhật phải duy trì MBR bao đủ dữ liệu.

**Suy giảm hiệu quả và sai kết quả không giống nhau.** Hộp bao cũ **rộng hơn cần thiết** có thể gây duyệt dư; hộp bao quá nhỏ **thiếu dữ liệu** có thể gây false negative. Tombstone phải che bản base đã xóa; delta phải ghi đè bản base khi một ID thay vị trí; nearest neighbor không được dùng ứng viên stale để cắt nhánh.

Với hệ thống cập nhật nhiều nhưng cần chỉ mục tĩnh nhanh, một thiết kế hữu ích là **base + delta + tombstones**:

\[
\boxed{
\mathcal D =
\{(id,B[id]):id\in\operatorname{keys}(B)\setminus
(T\cup\operatorname{keys}(\Delta))\}
\;\cup\;
\{(id,\Delta[id]):id\in\operatorname{keys}(\Delta)\}.
}
\]

Đây là **phép hợp các bản ghi sau khi loại khóa đã bị xóa hoặc ghi đè**, không phải phép cộng các danh sách tùy ý: mỗi ID chỉ có **một tọa độ hiện hành**. Rebuild định kỳ tạo chỉ mục mới từ \(\mathcal D\), làm gọn tombstone và có thể phục hồi AABB chọn lọc hơn. Nếu có update đồng thời, việc build và swap phải sử dụng **snapshot/version/replay** để không mất thay đổi mới.

**Đánh giá thực tế** cần cùng lúc kiểm tra kết quả với quét tuyến tính và đo **node visits, bucket occupancy, MBR overlap, số kết quả k, thời gian build/update/rebuild, bộ nhớ, I/O và p95/p99**. Không có chỉ mục nào bảo đảm truy vấn \(O(\log n)\) cho mọi phân bố, mọi metric và mọi số kết quả.

> Chọn một chỉ mục không gian tốt là chọn cấu trúc **giữ đúng dữ liệu đang sống**, **cắt tỉa hiệu quả theo workload hiện tại** và **có chi phí cập nhật/bảo trì phù hợp**. Khi phân bố dữ liệu hoặc truy vấn thay đổi, phải đánh giá lại cấu hình, chính sách rebuild và thậm chí chính lựa chọn cấu trúc.
