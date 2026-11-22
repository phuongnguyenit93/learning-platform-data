# Chặn khối trong phép xử lý ma trận và dãy

**Chặn khối** (*blocking/tiling*) là cách chia dữ liệu và phép tính thành các **khối vừa với bộ nhớ nhanh** để tăng **tính cục bộ truy cập** (*locality of reference*), giảm việc mang đi mang lại dữ liệu giữa các tầng bộ nhớ. Ý tưởng cốt lõi không phải thay công thức toán học của bài toán mà là **đổi thứ tự và phạm vi thực hiện phép tính** sao cho một khối dữ liệu đã tải vào cache/RAM được **tái sử dụng nhiều lần trước khi bị đẩy ra**.

Với ma trận lưu **row-major**, truy cập liên tiếp theo cột thay vì theo hàng có thể làm rất nhiều cache line hoặc trang bộ nhớ được tải chỉ để dùng một số ít phần tử. Với dữ liệu **ngoài RAM**, truy cập ngẫu nhiên từng phần tử còn có thể tạo nhiều yêu cầu đọc đĩa/SSD và tăng seek/IOPS. Chia khối giúp biến phần việc thành các lần đọc/ghi tuần tự hoặc những *tile* được tái sử dụng, thay vì liên tục đi qua toàn bộ dữ liệu lớn theo thứ tự bất lợi.

Ví dụ quen thuộc:
- Nhân hai ma trận chữ nhật `A_{m×p}·B_{p×n}`: tích mỗi ô cần nhiều phần tử A và B, nhưng có thể **nhân từng tile** và cộng dồn vào tile kết quả.
- Chuyển vị ma trận: phải đổi cả hàng thành cột, gây truy cập **bước nhảy lớn** nếu đi theo cách ngây thơ; dùng tile vuông giúp giới hạn vùng làm việc.
- Tổng tiền tố của một dãy: mỗi khối có thể tính **prefix cục bộ**, sau đó dùng tổng các khối trước để **điều chỉnh offset** cho đúng.
- Tính tổng cửa sổ, convolution hoặc stencil: mỗi tile kết quả cần **vùng chồng lấn (halo)** của đầu vào; bỏ halo làm sai kết quả ở biên.

Bài thuộc nhóm **Ngoài bộ nhớ** của **Computer Science Algorithms**, đề bài **Chặn khối trong phép xử lý ma trận và dãy**. Vì vậy ta sẽ phân biệt **cache blocking khi tất cả dữ liệu đã nằm trong RAM** với **out-of-core/external-memory blocking khi dữ liệu không vừa RAM**, trình bày mô hình I/O với bộ nhớ nhanh M và đơn vị chuyển B, phân tích điều kiện chọn tile size và đường truy cập, minh họa bằng **chương trình Java 17+ chạy độc lập**, và kiểm tra bằng hàng trăm nghìn lượt đối chiếu với thuật toán tham chiếu.

**Mục tiêu:** đọc được một vòng lặp ma trận và chỉ ra stride/tái sử dụng dữ liệu; tự viết loop tiling cho nhân và chuyển vị ma trận chữ nhật, không bỏ sót phần khối cuối; hiểu vì sao **blocking không tự giảm `O(mpn)` phép nhân-cộng**; tính đúng offset và halo cho dãy; biết khi nào cần dùng **FileChannel/stream/buffer tile thật** thay vì chỉ đổi vòng lặp trên mảng RAM; chọn cỡ khối bằng mô hình bộ nhớ và đo thực nghiệm; xử lý padding, overflow, aliasing, biên và trường hợp một chiều bằng 0.

## 1. Bối cảnh: bộ nhớ là nhiều tầng, không phải một mảng phẳng

Một chương trình Java nhìn thấy `long[]` như một mảng phẳng, nhưng phần cứng thực hiện các lần đọc/ghi qua những tầng có tốc độ và dung lượng rất khác nhau:

1. **Thanh ghi và bộ nhớ cache nhỏ** (thường L1): nhanh, dung lượng hạn chế.
2. **Các tầng cache lớn hơn** (L2, LLC/L3): chậm hơn nhưng chứa được nhiều dữ liệu.
3. **RAM:** chứa heap và các cấu trúc lớn, nhưng băng thông/độ trễ khác cache.
4. **SSD/HDD hoặc lưu trữ từ xa:** dung lượng lớn, chi phí một truy cập nhỏ ngẫu nhiên thường đắt hơn nhiều so với đọc tuần tự.
5. **Mạng/phân tán:** khi dữ liệu trên worker khác, phép chuyển còn có latency và serialization.

Khi CPU dùng một phần tử từ mảng, hệ thống thường mang cả một **cache line** vào cache, không chỉ vài byte của phần tử đó. Khi ứng dụng đọc file, hệ điều hành và thiết bị lưu trữ cũng xử lý theo **page/block/buffer** có kích thước hữu hạn.

Vì vậy **cùng một số phép toán số học** có thể có thời gian chạy rất khác nhau nếu một cách:
- Liên tục sử dụng những phần tử gần nhau trong RAM;
- Giữ được A/B/C tile trong cache;
- Đọc file theo các khối liên tiếp;
- Tránh chuyển dữ liệu giữa bộ nhớ chậm và nhanh nhiều lần.

### Ví dụ locality theo hàng và cột

Một ma trận `m×n` dùng `long[]` row-major có vị trí:

**`index(i,j)=i·n+j`**.

Với một phần tử long thường chiếm 8 byte, hai giá trị `A[i][j]` và `A[i][j+1]` kề nhau trong mảng phẳng. Nếu đi tiếp `A[i+1][j]`, địa chỉ tăng khoảng **`n·8 byte`** thay vì 8 byte.

Ví dụ n=4096:
- Đi theo hàng, mỗi bước trong j di chuyển **8 byte**.
- Đi theo cột, mỗi bước trong i di chuyển **4096·8=32768 byte**.

Nếu cache line có 64 byte thì về mặt kích thước có thể chứa 8 long liên tiếp. Một vòng lặp theo hàng có cơ hội dùng nhiều long trên cùng cache line; vòng theo cột có thể khiến mỗi bước truy cập một line/trang khác. **Số cache miss thực tế còn phụ thuộc bộ nhớ, prefetcher, liên kết cache, layout, kích thước dữ liệu và những truy cập khác**, nên không được từ chênh lệch stride tự suy ra tỷ lệ tăng tốc chính xác.

## 2. Mô hình I/O: M và B

Để phân tích thuật toán **ngoài bộ nhớ**, ta thường dùng mô hình hai tầng:
- **`M`:** số phần tử dữ liệu có thể giữ trong **bộ nhớ nhanh**.
- **`B`:** số phần tử liên tiếp được chuyển trong **một I/O block**.
- Dữ liệu còn lại ở **bộ nhớ chậm**.
- **Chi phí I/O** là số lần chuyển block giữa hai tầng, không chỉ số phép cộng/nhân CPU.

Lưu ý: ở đây **M và B được tính theo số phần tử**, không phải byte. Nếu một phần tử dùng s byte và có RAM ngân sách R byte, có thể ước tính `M≈R/s` sau khi đã trừ overhead, scratch, runtime và dữ liệu khác.

### Quét tuần tự một dãy

Nếu có N phần tử nằm liên tiếp trên lưu trữ, mỗi I/O đọc được B phần tử, một lần quét cần khoảng:

**`⌈N/B⌉` lần chuyển block**, tức **`Θ(N/B)` I/O** trong mô hình lý tưởng.

Vẫn phải thực hiện Θ(N) lượt xử lý CPU nếu cần xem mọi phần tử. **Blocking không biến N phép cộng thành N/B phép cộng**; nó giảm số lần truy cập **tầng chậm** theo đơn vị block.

### Truy cập ngẫu nhiên có thể đắt hơn

Nếu các lần truy cập rải ra nhiều block và ít tái sử dụng, một phép truy cập có thể gây một lần chuyển block, khiến số I/O gần với số phần tử được truy cập thay vì N/B. Trong thực tế, page cache/prefetch và thiết bị SSD có thể thay đổi kết quả, nhưng ý tưởng locality vẫn còn giá trị.

### Blocking trong cache và ngoài RAM khác nhau

**Cache tiling:** dữ liệu A, B, C đều được giữ trong các mảng heap RAM; ta chỉ sắp xếp vòng lặp để CPU sử dụng cache tốt hơn. **Không có nghĩa chương trình đã dùng thuật toán out-of-core**.

**Out-of-core tiling:** dữ liệu thực sự nằm ở file/thiết bị hoặc một tập dữ liệu vượt RAM; chương trình chỉ tải một số tile vào buffer RAM, xử lý, ghi lại rồi giải phóng/đổi buffer. Phải quản lý **read/write offsets, I/O block alignment, eviction, persistence, buffer capacity**. Chỉ đổi vòng for trong code Java dùng ba `long[]` lớn **không** tự làm dữ liệu vượt RAM trở nên chạy được.

## 3. Các thuật ngữ cần phân biệt

**Block:** nhóm dữ liệu được xử lý như một đơn vị. Kích thước khối có thể nói theo **phần tử**, **byte**, **hàng/cột** hoặc **số trang**. Cần ghi rõ đơn vị.

**Tile:** một khối con hai chiều (hoặc nhiều chiều) của ma trận/tensor, thường có kích thước `b_i×b_j`. Từ “tile” giúp phân biệt vùng hình chữ nhật trong không gian chỉ số với block I/O vật lý.

**Panel:** một dải dài, ví dụ A[i0:i1,k0:k1] hoặc B[k0:k1,j0:j1], dùng khi nhân ma trận.

**Working set:** lượng dữ liệu mà một pha tính toán cần giữ gần nhau để tận dụng tái sử dụng.

**Packing:** sao chép một tile/panel từ layout gốc có stride bất lợi sang một buffer liên tục, dễ vectorize hoặc truy cập theo hàng; tốn chi phí copy nhưng có thể giúp khi tile được dùng lại nhiều lần.

**Halo/ghost cells:** những phần tử ngoài tile đầu ra nhưng **cần đọc** để tính kết quả tại biên tile, ví dụ cửa sổ chiều rộng w hoặc stencil 2D.

**Prefetch/double buffering:** chuẩn bị tile kế tiếp khi đang xử lý tile hiện tại, với giả thiết có I/O bất đồng bộ hoặc cơ chế pipeline phù hợp; cần thêm buffer và đồng bộ.

**Blocking factor b:** số phần tử/hàng/cột trong một chiều khối. Không phải luôn chọn một b cho mọi chiều; ma trận chữ nhật hoặc cache/vector width khác nhau có thể cần ba tham số `b_i,b_j,b_k`.

## 4. Chặn khối ma trận nhân: bắt đầu từ công thức

Cho:

**`A∈ℤ^{m×p}`** và **`B∈ℤ^{p×n}`**.

Ma trận tích `C=A·B` có kích thước **`m×n`**, với:

**`C[i,j]=Σ_{k=0}^{p−1}A[i,k]·B[k,j]`**.

### Thuật toán tham chiếu ba vòng

~~~text
for i = 0..m-1:
    for j = 0..n-1:
        sum = 0
        for k = 0..p-1:
            sum += A[i,k] * B[k,j]
        C[i,j] = sum
~~~

Tổng phép nhân/cộng khoảng **`Θ(mpn)`**. Khi B ở dạng row-major, vòng k bên trong đọc B[k,j] với stride n, có thể bất lợi cho cache. Mỗi kết quả C[i,j] cũng độc lập, nhưng dữ liệu A và B có thể bị đọc lại rất nhiều giữa các ô.

### Đổi thứ tự vòng lặp: i-k-j

~~~text
initialize C to zeros
for i = 0..m-1:
    for k = 0..p-1:
        aik = A[i,k]
        for j = 0..n-1:
            C[i,j] += aik * B[k,j]
~~~

Ưu điểm:
- `A[i,k]` chỉ tải một lần trong vòng j bên trong.
- `B[k,j]` đi theo **hàng B liên tục**.
- `C[i,j]` cũng được cập nhật liên tiếp theo j.

Nhược điểm: nếu cả một hàng B/C quá dài để giữ tốt trong cache hoặc nhiều hàng B liên tục được quét lại cho mỗi i, dữ liệu vẫn có thể bị thay ra liên tục. **Loop reordering** là một tối ưu cục bộ; **tiling** giới hạn working set hơn nữa.

## 5. Nhân ma trận theo tile

Chọn một block size `b≥1`. Chia ba chiều thành từng đoạn:

- `i∈[i0,min(m,i0+b))`.
- `k∈[k0,min(p,k0+b))`.
- `j∈[j0,min(n,j0+b))`.

Với từng bộ tile (i0,k0,j0), cộng đóng góp của panel A và panel B vào tile C tương ứng.

Pseudocode:

~~~text
C = zero matrix(m,n)

for i0 in blocks(0,m,b):
    for k0 in blocks(0,p,b):
        for j0 in blocks(0,n,b):
            for i in [i0, min(m,i0+b)):
                for k in [k0, min(p,k0+b)):
                    aik = A[i,k]
                    for j in [j0, min(n,j0+b)):
                        C[i,j] += aik * B[k,j]
~~~

Điều quan trọng:
1. **`C` khởi tạo bằng 0** đúng một lần.
2. Mọi **k tile** đóng góp vào cùng C[i,j] phải được cộng dồn; không được gán đè kết quả C khi chuyển sang k0 tiếp theo.
3. Tile cuối có thể nhỏ hơn b; dùng min/chặn biên thay vì giả định kích thước chia hết cho b.
4. Cần đúng thứ tự **i,k,j** trong các vòng trong nếu muốn đọc B và cập nhật C liên tục theo j.
5. Hàng A và B có thể dùng lại trong một tile; thời gian thực tế phụ thuộc b, layout và cache.

### Chứng minh không mất hoặc đếm đôi tích

Một phép hạng `A[i,k]·B[k,j]` ứng với một bộ ba chỉ số hợp lệ (i,k,j). Tập chỉ số i, k, j được phân hoạch thành các khối không chồng nhau theo từng chiều, nên bộ ba này thuộc **duy nhất một** tổ hợp tile (i0,k0,j0).

Các vòng trong của tile đó tính đúng phép hạng và cộng vào C[i,j]. Vì mọi bộ ba được xét một lần, sau tất cả tile ta có đúng:

**`C[i,j]=Σ_kA[i,k]·B[k,j]`**.

Chứng minh này dựa vào số học nguyên chính xác/không overflow. Nếu sử dụng `double`, việc đổi thứ tự các phép cộng có thể thay đổi sai số làm tròn; kết quả có thể **khác bit** dù cùng công thức thực.

### Matrix dimensions phải khớp

Nếu A là m×p và B là q×n, phép nhân chỉ hợp lệ khi **p=q**. Không được lặng lẽ dùng min(p,q) để bỏ phần dư, vì như vậy đổi bài toán.

Với p=0, tích theo quy ước có tổng rỗng bằng 0, C là ma trận zero m×n. Code mẫu hỗ trợ tình huống này bằng cách lưu riêng số hàng/cột, không suy shape chỉ từ chiều dài flat array.

## 6. Ví dụ nhân ma trận chữ nhật

Cho:

~~~text
A (2x3) = [
  [1, 2, 3],
  [4, 5, 6]
]

B (3x2) = [
  [ 7,  8],
  [ 9, 10],
  [11, 12]
]
~~~

Ma trận tích:

**`C[0,0]=1·7+2·9+3·11=58`**.

**`C[0,1]=1·8+2·10+3·12=64`**.

**`C[1,0]=4·7+5·9+6·11=139`**.

**`C[1,1]=4·8+5·10+6·12=154`**.

Kết quả:

~~~text
C (2x2) = [
  [ 58,  64],
  [139, 154]
]
~~~

Với tile size b=2:
- i chỉ có một tile [0,2).
- k được chia thành [0,2) và [2,3).
- j có một tile [0,2).

Sau k tile đầu, C có đóng góp của k=0,1; sau k tile sau, cộng thêm k=2. Phần k cuối chỉ dài 1, nhưng không có phần tử nào bị bỏ.

**Không** chỉ test ma trận vuông n×n chia hết cho b. Chính các kích thước 2×3, 3×2 làm lộ lỗi ở những tile cuối không đầy.

## 7. Chọn block size b theo working set

Xét tile vuông b×b của A, B và C, mỗi phần tử dùng s byte. Một ước lượng thô để giữ **ba tile** trong bộ nhớ nhanh là:

**`3·b²·s ≤ M_bytes`**.

Nếu s=8 byte cho long và ngân sách gần 32 KiB:

**`3·32²·8=24.576 byte≈24 KiB`**.

Vì vậy b=32 là một điểm thử có cơ sở, **không phải tối ưu mặc định**. Cần chừa bộ nhớ cho stack, code, tags, biến khác và cache associativity; ma trận thực tế còn có stride và alignment.

### Không đồng nhất tile working set với cấp phát mới

Chương trình Java bên dưới **không copy riêng** ba tile ra ba buffer; nó truy cập những dải của mảng A/B/C sẵn có. Công thức 3b²s mô tả lượng dữ liệu logic cần giữ gần nhau trong cache, không phải lượng bộ nhớ đã được JVM cấp phát cho ba tile.

Nếu muốn **out-of-core** thật, cần **cấp buffer tile** rồi đọc từ file; khi đó ước lượng RAM trở thành ràng buộc cấp phát thực. Cần cộng buffer I/O, output, metadata và số tile hoạt động đồng thời.

### Tại sao b quá nhỏ cũng không tốt?

Nếu b=1, mỗi tile chỉ xử lý một phép nhân-cộng: không tận dụng được nhiều tái sử dụng, tăng số lần đi qua cấu trúc vòng và overhead. Với b lớn hơn, có thể giảm số lần tải lại các panel.

### Tại sao b quá lớn có thể chậm?

Nếu ba tile không vừa trong cache phù hợp, các dòng cache mới đẩy các dòng đang được dùng ra, tạo **capacity misses**. Tile lớn cũng làm vùng update C và B trải trên nhiều dòng bộ nhớ; vectorization/TLB/NUMA có thể bị ảnh hưởng.

### Tại sao không có b “đúng” cho mọi máy?

Block size phụ thuộc:
- L1/L2/L3 và cache line của máy.
- Độ dài vector SIMD và thư viện BLAS/JIT.
- Kích thước loại phần tử float/double/long.
- Shape m,p,n và tỷ lệ các chiều.
- Số thread, mức chia sẻ LLC.
- Row-major, column-major, packed panel.
- Ngân sách RAM/page size/throughput thiết bị.
- Cách benchmark và thực tế dữ liệu có vừa cache hay không.

Một giải pháp hiệu năng cao thường dùng **multi-level blocking**, ví dụ tile lớn cho LLC và tile nhỏ cho L1/SIMD, không chỉ một b.

## 8. Blocking không làm giảm số phép toán đại số

Nhân ma trận cổ điển vẫn xét m·p·n phép nhân (ngoại trừ các tối ưu bỏ qua zero hoặc thuật toán nhân ma trận khác). Blocking chỉ **sắp xếp lại** chúng.

**Thời gian tính toán đại số:** **`Θ(mpn)`** với thuật toán nhân ma trận thông thường.

**Lợi ích kỳ vọng:** ít cache miss/ít block I/O hơn, tăng throughput CPU, giảm số lần tải lại dữ liệu và tăng khả năng vector hóa khi viết đúng dạng.

Không thể từ phân tích tile suy ra “đã đổi phép nhân ma trận `O(n³)` thành `O(n²)`”. Nếu muốn giảm số phép nhân trong mô hình đại số, đó là nhóm thuật toán khác như Strassen (với các giả thiết/đánh đổi riêng), không phải chỉ loop tiling.

### Cận I/O kinh điển cho nhân ma trận vuông

Trong một mô hình bộ nhớ ngoài lý tưởng, tính nhân ma trận n×n **bằng thuật toán cổ điển** với M phần tử bộ nhớ nhanh và chuyển mỗi block B phần tử, một cận chi phí chuyển dữ liệu có dạng:

**`Ω(n³/(B·√M)+n²/B)`**,

theo những điều kiện thường dùng về mô hình I/O, khả năng khởi tạo/lưu output và thuật toán cổ điển. Với tile b≈√M và cách tổ chức I/O phù hợp, blocking có thể **tiệm cận cận này** về bậc I/O. Những hằng số, điều kiện “tall cache”, block alignment, layout file và giới hạn RAM phải được phân tích riêng.

**Đừng áp công thức này máy móc** cho mọi nhân ma trận chữ nhật, mọi thư viện hay thuật toán nhân nhanh; cũng không coi đây là số lần Java gọi `get()`. Nó là mô hình đếm **chuyển block giữa hai tầng bộ nhớ**.

### Đếm thô cho tile out-of-core

Với ma trận vuông chia gần đều thành (n/b) tile mỗi chiều:
- Có khoảng `(n/b)³` bộ ba tile A/B/C được nhân và cộng.
- Mỗi bộ ba dùng O(b²) phần tử đầu vào.
- Nếu giữ C tile trong RAM qua toàn bộ k0, giảm số lần đọc/ghi C.
- Lượng dữ liệu tải A/B thô ~`O((n/b)³·b²)=O(n³/b)` phần tử; nếu các tile được lưu và tải theo block liên tục thì tương đương ~`O(n³/(bB))` block I/O, cộng chi phí đọc/ghi kết quả.

Đây là **ước lượng mô hình** dưới layout/buffer phù hợp, không phải cam kết cho file row-major bất kỳ. Đọc một tile từ nhiều hàng xa nhau có thể cần nhiều truy cập nhỏ hoặc seek; **physical layout** quyết định hiệu quả.

## 9. Cache blocking vs out-of-core: hai vòng lặp khác nhau

### Khi các ma trận đều có trong RAM

Code demo giữ:
- A trong `long[]`;
- B trong `long[]`;
- C trong `long[]`.

Ba mảng tổng cộng cần **`8·(mp+pn+mn)` byte dữ liệu long** (chưa tính object overhead). Nếu chúng vừa RAM, loop tiling chủ yếu cố tối ưu **cache**.

### Khi ma trận vượt RAM

Một kiến trúc out-of-core hợp lý có thể dùng thứ tự:

~~~text
for each output tile (i0,j0):
    Ctile = zero or read existing output tile
    for each inner tile k0:
        Atile = readTile(fileA, i0, k0)
        Btile = readTile(fileB, k0, j0)
        Ctile += Atile * Btile
    writeTile(fileC, i0, j0, Ctile)
~~~

Ý nghĩa:
- Ctile được **giữ trong RAM** trong suốt tất cả k0.
- Sau khi cộng xong mọi đóng góp, chỉ **ghi Ctile một lần**.
- A/B tile được nạp theo nhu cầu; có thể cache panel ở cấp cao hơn để giảm đọc lặp.
- Bộ nhớ RAM phải đủ cho các tile đang hoạt động, metadata và bộ đệm đọc/ghi.

Nếu output file cần tồn tại từ trước, phải định nghĩa rõ việc zero-initialize/overwrite và crash recovery; không dùng nội dung file chưa khởi tạo làm accumulator.

**Code Java chạy được ở mục 19 là cache-tiled in-memory**, không thực hiện readTile/writeTile từ file. Việc dùng pseudocode out-of-core ở đây giúp hiểu cách nâng cấp thiết kế, **không** được xem code demo là một bộ xử lý ma trận lớn hơn RAM.

## 10. File layout và truy cập tile

Một ma trận lưu row-major trong file chứa các hàng nối tiếp. Một tile b×b nằm trong:
- b phần của b hàng khác nhau;
- mỗi đoạn hàng có b phần tử liên tiếp;
- khoảng cách giữa hai đoạn hàng theo stride n.

Đọc tile như một block b² phần tử liên tục có thể **sai**, trừ khi file đã được lưu theo **blocked layout**. Với row-major phải đọc b đoạn hàng tại đúng offsets hoặc dùng một buffer strip đã giải mã.

Các lựa chọn:

**Row-major file:** dễ đọc tuần tự từng hàng, nhưng đọc các tile hẹp có thể tạo nhiều I/O nhỏ.

**Tiled file layout:** lưu các tile theo một thứ tự được chọn, ví dụ các tile hàng trước; một tile có thể được đọc bằng một hoặc vài I/O lớn. Thường có thêm metadata/offset mapping.

**Memory-mapped file:** có thể truy cập file như bộ nhớ ảo nhưng **không đảm bảo** locality hoặc RAM usage tự tốt. Page faults vẫn xảy ra; cần pattern truy cập đúng và chú ý hành vi map/unmap.

**ByteBuffer/FileChannel:** phù hợp Java để đọc một vùng file vào buffer có dung lượng hữu hạn. Với `long` cần đồng nhất **endianness**, kiểm số byte đọc, EOF, short read, file offset và giới hạn kích thước buffer.

### Nên align tile theo B không?

Nếu một block I/O vật lý chứa B phần tử, đọc tile bằng những đoạn có kích thước b không phù hợp có thể gây I/O thừa. Nên chọn:
- kích thước đoạn đọc/ghi là bội số hợp lý của page/block/buffer khi có thể;
- tile shape hợp lý với file layout;
- double buffering nếu thiết bị và runtime cho phép overlap đọc/ghi với tính toán.

Không có một quy tắc “tile size bằng page size” đúng cho cả bài: **tile dữ liệu** có thể là hàng nghìn phần tử và chứa nhiều page vật lý.

## 11. Chuyển vị ma trận: một phép toán không nhân nhưng rất nhạy locality

Cho A kích thước m×n. Ma trận chuyển vị `T=Aᵀ` có kích thước n×m:

**`T[j,i]=A[i,j]`**.

Độ phức tạp tính toán có cận **Θ(mn)** vì phải ghi mn phần tử vào kết quả, nhưng hiệu năng bộ nhớ có thể rất khác theo thứ tự lặp.

### Phiên bản tham chiếu

~~~text
for i = 0..m-1:
    for j = 0..n-1:
        T[j,i] = A[i,j]
~~~

Trong row-major:
- Đọc A[i,j] theo j là **liên tục**.
- Ghi T[j,i] theo j nhảy một bước stride m.
- Nếu m lớn, các lần ghi liên tiếp có thể đụng nhiều cache lines/pages khác nhau.

Đổi thành j ngoài và i trong sẽ giúp ghi T liên tục nhưng làm **đọc A có stride n**. Không thể đồng thời tuyến tính hóa cả đọc và ghi bằng một thứ tự vòng đơn giản cho mọi shape.

### Chuyển vị theo tile

~~~text
for i0 in blocks(0,m,b):
    for j0 in blocks(0,n,b):
        for i in [i0,min(m,i0+b)):
            for j in [j0,min(n,j0+b)):
                T[j,i] = A[i,j]
~~~

Một tile đầu vào b×b và một tile output tương ứng b×b có thể được tái sử dụng trong vùng cache hữu hạn. Trong tile, một phía vẫn có stride, nhưng toàn bộ working set được hạn chế và thường được xử lý trước khi đi tile khác.

Công thức indexing:
- A row-major index: **`i·n+j`**.
- T row-major index: **`j·m+i`**.

Nếu nhầm `j·n+i`, chỉ những bài vuông tình cờ có cùng m=n mới có thể che lỗi; với ma trận chữ nhật rất dễ sai.

### Ví dụ 2×3

~~~text
A = [
  [1, 2, 3],
  [4, 5, 6]
]

transpose(A) = [
  [1, 4],
  [2, 5],
  [3, 6]
]
~~~

T kích thước **3×2**, không phải 2×3.

### In-place transpose khó hơn

Đối với ma trận vuông liên tục, có thể viết thuật toán đổi chỗ các cặp đối xứng qua đường chéo; blocked in-place transpose cần cẩn thận với hai tile (i,j) và (j,i), không được ghi đè dữ liệu chưa đọc.

Đối với **ma trận chữ nhật**, việc chuyển vị **in-place** trên một mảng phẳng là một phép hoán vị chỉ số không đơn giản; không thể chỉ đổi metadata rows/cols mà giữ y nguyên mảng nếu vẫn muốn nội dung theo row-major của T. Demo chọn **output mới**, bảo toàn A.

## 12. Dãy một chiều: blocking không chỉ là cắt thành từng phần độc lập

Với một dãy `a₀,...,a_{N−1}`, chia thành khối:

**`[0,b),[b,2b),...`**,

khối cuối có thể ngắn hơn b. Cách này rất hữu ích khi:
- đọc file theo buffer thay vì `read()` từng byte;
- xử lý dữ liệu trên CPU theo các tile vừa cache;
- làm việc song song từng chunk;
- giới hạn memory cho một pipeline;
- tái sử dụng kết quả tạm trong một vùng nhỏ.

Nhưng có hai nhóm phép toán:
1. **Độc lập theo khối:** ví dụ mỗi phần tử biến đổi `f(a_i)`, có thể xử lý từng khối mà không cần dữ liệu từ khối khác.
2. **Phụ thuộc giữa khối:** ví dụ prefix sum, moving average, cửa sổ, stencil. Nếu bỏ thông tin biên, kết quả sẽ **sai**.

Chủ đề **“chặn khối trong phép xử lý ma trận và dãy”** yêu cầu đặc biệt chú ý nhóm thứ hai.

## 13. Tổng tiền tố theo khối: tách phép tính và ghép offset

Định nghĩa prefix sum inclusive:

**`p[i]=Σ_{j=0}^{i}a[j]`**.

Ví dụ:

~~~text
a = [3, -1, 4, -2, 5]
p = [3,  2, 6,  4, 9]
~~~

Nếu chia khối b=2:

~~~text
Block 0: [ 3,-1]      local prefix = [3,2], total=2
Block 1: [ 4,-2]      local prefix = [4,2], total=2
Block 2: [ 5]         local prefix = [5],   total=5
~~~

Gộp bằng offset:
- Block 0 có carry trước nó =0, giữ [3,2].
- Block 1 có carry=2, sửa [4,2] thành **[6,4]**.
- Block 2 có carry=2+2=4, sửa [5] thành **[9]**.

Kết quả toàn dãy: **[3,2,6,4,9]**.

### Thuật toán hai pha

**Pha 1:** tính prefix cục bộ cho từng khối và tổng của từng khối.

**Pha 2:** chạy qua các khối theo thứ tự, duy trì `carry` là tổng tất cả các khối **trước khối hiện tại**, cộng carry vào mọi prefix cục bộ của khối, rồi cập nhật carry += tổng khối.

Pseudocode:

~~~text
for each block q:
    running = 0
    for i in block q:
        running += a[i]
        output[i] = running
    total[q] = running

carry = 0
for each block q in increasing order:
    for i in block q:
        output[i] += carry
    carry += total[q]
~~~

### Chứng minh đúng

Một index i thuộc khối q. Tổng tiền tố toàn cục chia thành:
- tổng tất cả phần tử của các khối trước q;
- tổng những phần tử từ đầu khối q đến i.

Phần thứ nhất chính là carry; phần thứ hai chính là localPrefix[i]. Do đó:

**`globalPrefix[i]=carryBeforeBlock(q)+localPrefix[i]`**.

Cách tính không thiếu hoặc đếm đôi phần tử.

### Khi nào cách hai pha đáng dùng?

Dạng hai pha có ích khi muốn **song song hóa local scan**, ghi block totals rồi xử lý offsets, hoặc xử lý dữ liệu trên các chunk khác nhau.

**Không mặc định hai pha tốt hơn streaming một lượt:** nếu chỉ muốn prefix sum tuần tự, một biến `running` cập nhật xuyên khối đã đủ O(N) thời gian, O(1) state và một lần đọc. Bản Java dùng hai pha **để minh họa phụ thuộc liên khối** và cách ghép đúng, không tuyên bố giảm số thao tác so với vòng for đơn giản.

### Tổng tiền tố với overflow

Code dùng `Math.addExact` cho long để phát hiện overflow. Nếu mọi prefix toàn cục nằm trong long nhưng một **local block prefix tạm thời** vượt long rồi sau đó được bù bởi carry âm ở khối trước, chương trình vẫn có thể ném lỗi. Vì vậy hợp đồng demo cần bảo đảm **mọi tổng trung gian mà từng pha tính đều biểu diễn được bằng long**, hoặc dùng BigInteger nếu muốn hỗ trợ toàn bộ miền toán học.

## 14. Cửa sổ trượt và halo giữa các khối

Một truy vấn cửa sổ có chiều rộng w≥1:

**`s[i]=a[i]+a[i+1]+...+a[i+w−1]`**,

với `0≤i≤N−w`.

Số output khi w≤N là:

**`count=N−w+1`**.

Nếu w>N, không có cửa sổ đầy đủ và output là mảng rỗng theo hợp đồng demo.

### Vì sao mỗi tile output cần halo?

Giả sử ta chia **các chỉ số output** thành khối:

**`i∈[s,e)`**.

Để tính mọi s[i] trong tile này, cần những phần tử input từ:

**`a[s] tới a[e+w−2]`**,

hay đoạn nửa mở:

**`input[s,e+w−1)`**.

Vùng output có e−s vị trí, nhưng input tile cần **`(e−s)+(w−1)`** phần tử. **w−1 phần tử cuối là halo bên phải** để những cửa sổ gần biên output vẫn đọc được dữ liệu ở khối kế tiếp.

### Ví dụ mảng 5 phần tử, w=3, tile output b=2

~~~text
a = [3, -1, 4, -2, 5]
s[0] = 3 + (-1) + 4  = 6
s[1] = -1 + 4 + (-2) = 1
s[2] = 4 + (-2) + 5  = 7

output = [6,1,7]
~~~

Với tile output đầu tiên [0,2), ta cần input [0,4), tức [3,−1,4,−2]; hai phần tử **4,−2** giúp tính output vị trí 1. Tile thứ hai [2,3) cần input [2,5), gồm [4,−2,5].

Nếu chỉ nạp đúng 2 item input cho tile output đầu rồi tính cả hai cửa sổ, phần s[0]/s[1] sẽ thiếu dữ liệu. Chỉ chia input thành các khối độc lập mà không truyền halo là sai.

### Cách tính trong một tile bằng prefix cục bộ

Với input tile [start,inputEnd), tạo:

**`localPrefix[0]=0`**,  
**`localPrefix[j+1]=localPrefix[j]+a[start+j]`**.

Cho output ở vị trí i trong [start,end):

**`s[i]=localPrefix[(i−start)+w]−localPrefix[i−start]`**.

Do mỗi tile có phần tử cần thiết, công thức đúng tại mọi biên. Code Java thực hiện cách này và chỉ dùng một buffer prefix cục bộ kích thước **`tileOutputSize+w`**.

### Phân tích overhead halo

Nếu có Q output và tile output size b, số tile khoảng `⌈Q/b⌉`. Mỗi tile đọc khoảng b+w−1 phần tử đầu vào; tổng số phần tử được xem có thể gần:

**`O(Q+⌈Q/b⌉·(w−1))`**,

thay vì O(Q) nếu có kỹ thuật **giữ overlap** giữa các tile. Nếu w lớn mà b rất nhỏ, overhead halo có thể đáng kể.

Với riêng **tổng cửa sổ** tuần tự, công thức rolling sum:

**`nextSum=currentSum−a[i]+a[i+w]`**

cho O(N) thời gian sau khi có cửa sổ đầu tiên, không cần tạo lại toàn bộ halo cho mỗi tile. Cách block-local prefix minh họa **cơ chế chia việc song song/out-of-core** và kiểm biên, không nhất thiết là giải pháp nhanh nhất cho phép toán này.

## 15. Halo trong stencil và convolution 2D

Với một stencil hai chiều bán kính r:
- Mỗi output pixel dùng các input trong một vùng phụ thuộc xung quanh (ví dụ kernel (2r+1)×(2r+1)).
- Tile output b×b cần input rộng khoảng **`(b+2r)×(b+2r)`** ở các tile không sát biên.
- Những pixel ở r mép phải/trái/trên/dưới là **halo/ghost zone**.

Cần định nghĩa rõ biên toàn ảnh:
- Zero-padding.
- Reflect/mirror.
- Replicate/clamp.
- Wrap-around (chu kỳ).
- Chỉ tính valid region.

Không được tự cho các giá trị ngoài ảnh bằng 0 nếu bài yêu cầu phản xạ hoặc valid convolution.

### Chi phí tái đọc halo

Các tile cạnh nhau có vùng halo chồng lấn. Nếu mỗi tile được tải riêng từ file, một số phần tử input có thể bị đọc nhiều lần. Để tối ưu, giữ các hàng/cột chồng lấn trong buffer, xử lý tile theo thứ tự thuận lợi, hoặc bố trí tile lớn vừa với RAM. Trade-off giữa tăng tile và tăng RAM cần đo.

### Parallel processing và cập nhật tại chỗ

Nếu stencil mỗi bước cần **dữ liệu ở trạng thái trước bước**, không được cho worker này ghi đè input trong lúc worker khác vẫn cần đọc giá trị cũ. Cần dùng **double buffer** (input và output riêng), đồng bộ theo iteration, hoặc một lịch cập nhật có chứng minh bảo toàn phụ thuộc.

Ví dụ chuyển vị cũng sử dụng output mới để tránh aliasing; nhân ma trận không được tùy tiện cho output C cùng vùng nhớ với A/B nếu thuật toán sẽ làm mất dữ liệu đầu vào.

## 16. Khối cuối không đầy: nguồn lỗi phổ biến nhất

Giả sử N=10 và b=4, các khối phải là:

**`[0,4),[4,8),[8,10)`**.

Khối cuối chỉ có 2 phần tử. Nếu luôn chạy vòng trong b bước mà không kiểm end, sẽ truy cập index 10/11 ngoài mảng. Nếu chỉ chạy floor(N/b) khối, sẽ **bỏ mất hai phần tử cuối**.

Cách viết ổn định cho mọi kích thước:

~~~text
start = 0
while start < N:
    end = start + min(blockSize, N - start)
    process [start,end)
    start = end
~~~

Công thức `start+min(b,N−start)` còn tránh một trường hợp **overflow int tạm thời** mà biểu thức `min(N,start+b)` có thể gặp nếu start+b vượt giới hạn int. Bản Java dùng dạng này.

Với ma trận, phải xử lý **cả ba chiều** i,k,j: m,p,n có thể không chia hết cho b và thậm chí bằng 0.

## 17. Tổ chức dữ liệu ma trận trong Java

Để kiểm soát locality, demo dùng ma trận dày đặc trong **một mảng `long[]` row-major**:

**`data[i·cols+j]`**.

Không dùng mặc định `long[][]` trong hot loop, vì Java array-of-arrays là nhiều object hàng riêng: thuận tiện đọc code nhưng layout toàn ma trận trong heap không nhất thiết là một vùng liên tục duy nhất. `long[]` cho một vùng liên tục và công thức index rõ ràng.

### Lợi ích và giới hạn của flat array

- Dễ kiểm shape/stride.
- Dễ duyệt theo hàng.
- Dễ nối với buffer/file format row-major.
- Giảm dereference giữa nhiều object hàng.

Nhưng:
- Java array bị giới hạn bởi kích thước int và thực tế RAM.
- `rows·cols` có thể overflow int nếu nhân trực tiếp; dùng **`Math.multiplyExact(rows,cols)`**.
- Bố trí thread có thể gây false sharing nếu nhiều thread ghi các vùng gần nhau trên cùng cache line.
- Với ma trận cực lớn hoặc sparse, cần cấu trúc khác như memory mapping, chunked arrays, CSR/CSC hoặc lưu file tile.

### Vì sao không cấp mảng bằng số phần tử b² cho toàn ma trận?

Cây/mảng kết quả có shape m×n thực. Tile chỉ là **phạm vi chỉ số** hoạt động tại một thời điểm, không làm thay đổi shape đầu ra. Nếu dữ liệu vượt RAM, việc cấp C toàn kích thước lại càng không khả thi; phải ghi output từng tile sang file.

## 18. Yêu cầu về độ đúng khi đổi thứ tự phép tính

### Với số nguyên chính xác

Nhân ma trận dùng các tổng tích; việc nhóm các số nguyên không đổi kết quả nếu không overflow. Bản demo dùng `long` và **`Math.addExact/Math.multiplyExact`** để phát hiện trường hợp không thể biểu diễn kết quả trung gian.

### Với float/double

Thứ tự cộng ảnh hưởng làm tròn; blocked multiply có thể cho kết quả khác phiên bản i-j-k từng bit, nhất là khi dữ liệu có giá trị lớn/nhỏ xen kẽ. Một bộ test số thực phải dùng tiêu chí sai số phù hợp như absolute/relative tolerance và xét trường hợp cancellation/NaN/Inf, chứ không khẳng định `Arrays.equals` luôn đúng.

### Với phép toán không kết hợp

Không được tùy ý blocking rồi đổi thứ tự nếu phép toán yêu cầu thứ tự nghiêm ngặt hoặc có side effects. Ví dụ tính toán có phụ thuộc trạng thái, đọc/ghi xen kẽ, hoặc phép trừ được nhóm sai có thể ra kết quả khác. **Chặn khối an toàn cần giữ phụ thuộc dữ liệu và ngữ nghĩa phép toán**, không chỉ giới hạn vòng lặp.

### Với lỗi overflow

`Math.addExact` ném `ArithmeticException` nếu cộng long vượt miền. Nó giúp tránh im lặng trả kết quả sai nhưng không làm thuật toán có số học vô hạn; với dữ liệu cần độ chính xác lớn hơn long, dùng BigInteger hoặc miền modulo theo yêu cầu.

Một triển khai có thể đã ghi một phần output trước khi gặp ArithmeticException; chương trình demo không cam kết **atomic rollback** khi xảy ra overflow.

## 19. Chương trình Java 17+ độc lập

Tệp **`BlockingMatrixArrayDemo.java`** bao gồm bốn phần:
1. **`multiplyBlocked`:** nhân ma trận chữ nhật theo tile i-k-j, trả một Matrix mới.
2. **`transposeBlocked`:** chuyển vị theo tile với output mới.
3. **`prefixBlocked`:** prefix sum theo hai pha local prefix + block offsets.
4. **`windowSumsBlocked`:** cửa sổ trượt chia theo output tile, tính prefix cục bộ trên input có **halo**.

Mỗi hàm có một **thuật toán tham chiếu không blocked**:
- Nhân i-j-k trực tiếp.
- Chuyển vị toàn ma trận trực tiếp.
- Prefix cộng một vòng.
- Cửa sổ tính lại tổng từ đầu cho từng vị trí.

Kiểm thử ngẫu nhiên so mỗi bản blocked với bản tham chiếu trên các shape, kích thước tile và trường hợp biên khác nhau. Không in một số liệu “tăng tốc” chưa benchmark: mục tiêu của chương trình là **đúng và hiểu cách chặn khối**, không giả lập hiệu năng cache.

~~~java
import java.util.Arrays;
import java.util.SplittableRandom;

public final class BlockingMatrixArrayDemo {
    // Flat, row-major dense matrix of long values.
    private static final class Matrix {
        final int rows;
        final int cols;
        final long[] data;

        Matrix(int rows, int cols) {
            if (rows < 0 || cols < 0) {
                throw new IllegalArgumentException(
                        "Negative matrix dimension");
            }
            this.rows = rows;
            this.cols = cols;
            this.data = new long[Math.multiplyExact(
                    rows, cols)];
        }

        static Matrix fromRows(long[][] values) {
            if (values == null) {
                throw new IllegalArgumentException(
                        "Null input");
            }
            int m = values.length;
            int n = m == 0 ? 0 : values[0].length;
            Matrix result = new Matrix(m, n);
            for (int i = 0; i < m; i++) {
                if (values[i] == null
                        || values[i].length != n) {
                    throw new IllegalArgumentException(
                            "Ragged matrix");
                }
                System.arraycopy(
                        values[i], 0, result.data, i * n, n);
            }
            return result;
        }

        long[][] toRows() {
            long[][] out = new long[rows][cols];
            for (int i = 0; i < rows; i++) {
                System.arraycopy(
                        data, i * cols, out[i], 0, cols);
            }
            return out;
        }
    }

    private static void checkBlock(int block) {
        if (block <= 0) {
            throw new IllegalArgumentException(
                    "Block size must be positive");
        }
    }

    // Independent reference: i-j-k, O(m*p*n).
    private static Matrix multiplyReference(
            Matrix a, Matrix b) {
        if (a.cols != b.rows) {
            throw new IllegalArgumentException(
                    "Incompatible matrix shapes");
        }
        Matrix c = new Matrix(a.rows, b.cols);

        for (int i = 0; i < a.rows; i++) {
            for (int j = 0; j < b.cols; j++) {
                long sum = 0L;
                for (int k = 0; k < a.cols; k++) {
                    long product = Math.multiplyExact(
                            a.data[i * a.cols + k],
                            b.data[k * b.cols + j]);
                    sum = Math.addExact(sum, product);
                }
                c.data[i * b.cols + j] = sum;
            }
        }
        return c;
    }

    // Cache-tiled in-memory multiplication: i0-k0-j0,
    // followed by i-k-j, with j contiguous.
    private static Matrix multiplyBlocked(
            Matrix a, Matrix b, int block) {
        checkBlock(block);
        if (a.cols != b.rows) {
            throw new IllegalArgumentException(
                    "Incompatible matrix shapes");
        }

        final int m = a.rows;
        final int p = a.cols;
        final int n = b.cols;
        Matrix c = new Matrix(m, n);

        for (int i0 = 0; i0 < m; ) {
            int iEnd = i0 + Math.min(block, m - i0);

            for (int k0 = 0; k0 < p; ) {
                int kEnd = k0 + Math.min(block, p - k0);

                for (int j0 = 0; j0 < n; ) {
                    int jEnd = j0 + Math.min(block, n - j0);

                    for (int i = i0; i < iEnd; i++) {
                        int aRow = i * p;
                        int cRow = i * n;

                        for (int k = k0; k < kEnd; k++) {
                            long aik = a.data[aRow + k];
                            int bRow = k * n;

                            for (int j = j0; j < jEnd; j++) {
                                long product = Math.multiplyExact(
                                        aik, b.data[bRow + j]);
                                int pos = cRow + j;
                                c.data[pos] = Math.addExact(
                                        c.data[pos], product);
                            }
                        }
                    }
                    j0 = jEnd;
                }
                k0 = kEnd;
            }
            i0 = iEnd;
        }
        return c;
    }

    private static Matrix transposeReference(Matrix a) {
        Matrix out = new Matrix(a.cols, a.rows);
        for (int i = 0; i < a.rows; i++) {
            for (int j = 0; j < a.cols; j++) {
                out.data[j * a.rows + i] =
                        a.data[i * a.cols + j];
            }
        }
        return out;
    }

    private static Matrix transposeBlocked(
            Matrix a, int block) {
        checkBlock(block);
        Matrix out = new Matrix(a.cols, a.rows);

        for (int i0 = 0; i0 < a.rows; ) {
            int iEnd = i0 + Math.min(
                    block, a.rows - i0);

            for (int j0 = 0; j0 < a.cols; ) {
                int jEnd = j0 + Math.min(
                        block, a.cols - j0);

                for (int i = i0; i < iEnd; i++) {
                    for (int j = j0; j < jEnd; j++) {
                        out.data[j * a.rows + i] =
                                a.data[i * a.cols + j];
                    }
                }
                j0 = jEnd;
            }
            i0 = iEnd;
        }
        return out;
    }

    private static long[] prefixReference(long[] a) {
        long[] out = new long[a.length];
        long running = 0L;
        for (int i = 0; i < a.length; i++) {
            running = Math.addExact(running, a[i]);
            out[i] = running;
        }
        return out;
    }

    // Two phases: local prefixes, then preceding-block offset.
    private static long[] prefixBlocked(
            long[] a, int block) {
        checkBlock(block);
        if (a == null) {
            throw new IllegalArgumentException("Null array");
        }
        int n = a.length;
        int blocks = n == 0 ? 0
                : 1 + (n - 1) / block;
        long[] out = new long[n];
        long[] blockTotals = new long[blocks];

        for (int q = 0; q < blocks; q++) {
            int start = q * block;
            int end = start + Math.min(block, n - start);
            long running = 0L;

            for (int i = start; i < end; i++) {
                running = Math.addExact(running, a[i]);
                out[i] = running;
            }
            blockTotals[q] = running;
        }

        long carry = 0L;
        for (int q = 0; q < blocks; q++) {
            int start = q * block;
            int end = start + Math.min(block, n - start);
            for (int i = start; i < end; i++) {
                out[i] = Math.addExact(out[i], carry);
            }
            carry = Math.addExact(
                    carry, blockTotals[q]);
        }
        return out;
    }

    private static long[] windowReference(
            long[] a, int width) {
        if (a == null || width <= 0) {
            throw new IllegalArgumentException(
                    "Invalid array or window");
        }
        int count = width > a.length ? 0
                : a.length - width + 1;
        long[] out = new long[count];

        for (int i = 0; i < count; i++) {
            long sum = 0L;
            for (int j = i; j < i + width; j++) {
                sum = Math.addExact(sum, a[j]);
            }
            out[i] = sum;
        }
        return out;
    }

    // Output block [start,end) reads input
    // [start, end+width-1), including right halo.
    private static long[] windowSumsBlocked(
            long[] a, int width, int block) {
        checkBlock(block);
        if (a == null || width <= 0) {
            throw new IllegalArgumentException(
                    "Invalid array or window");
        }

        int count = width > a.length ? 0
                : a.length - width + 1;
        long[] out = new long[count];

        for (int start = 0; start < count; ) {
            int end = start + Math.min(
                    block, count - start);
            int inputEnd = end + (width - 1);
            int length = inputEnd - start;

            long[] localPrefix = new long[length + 1];
            for (int j = 0; j < length; j++) {
                localPrefix[j + 1] = Math.addExact(
                        localPrefix[j], a[start + j]);
            }

            for (int i = start; i < end; i++) {
                int offset = i - start;
                out[i] = Math.subtractExact(
                        localPrefix[offset + width],
                        localPrefix[offset]);
            }
            start = end;
        }
        return out;
    }

    private static void assertSame(
            Matrix expected, Matrix actual) {
        if (expected.rows != actual.rows
                || expected.cols != actual.cols
                || !Arrays.equals(
                        expected.data, actual.data)) {
            throw new AssertionError(
                    "Matrix mismatch");
        }
    }

    private static void assertSame(
            long[] expected, long[] actual) {
        if (!Arrays.equals(expected, actual)) {
            throw new AssertionError("Array mismatch");
        }
    }

    private static void randomChecks() {
        SplittableRandom rng =
                new SplittableRandom(5182026L);
        int comparisons = 0;

        // 2500 scenarios * 4 block sizes = 10000 checks.
        for (int t = 0; t < 2500; t++) {
            int m = rng.nextInt(7);
            int p = rng.nextInt(8);
            int n = rng.nextInt(7);
            Matrix a = new Matrix(m, p);
            Matrix b = new Matrix(p, n);

            for (int i = 0; i < a.data.length; i++) {
                a.data[i] = rng.nextInt(-15, 16);
            }
            for (int i = 0; i < b.data.length; i++) {
                b.data[i] = rng.nextInt(-15, 16);
            }

            Matrix expected = multiplyReference(a, b);
            for (int block : new int[]{1, 2, 3, 8}) {
                assertSame(expected,
                        multiplyBlocked(a, b, block));
                comparisons++;
            }
        }

        // 3000 scenarios * 4 block sizes = 12000 checks.
        for (int t = 0; t < 3000; t++) {
            int m = rng.nextInt(14);
            int n = rng.nextInt(14);
            Matrix a = new Matrix(m, n);
            for (int i = 0; i < a.data.length; i++) {
                a.data[i] = rng.nextInt(-200, 201);
            }
            Matrix expected = transposeReference(a);
            for (int block : new int[]{1, 2, 4, 9}) {
                assertSame(expected,
                        transposeBlocked(a, block));
                comparisons++;
            }
        }

        // 3000 scenarios * 5 block sizes = 15000 checks.
        for (int t = 0; t < 3000; t++) {
            int n = rng.nextInt(81);
            long[] values = new long[n];
            for (int i = 0; i < n; i++) {
                values[i] = rng.nextInt(-100, 101);
            }
            long[] expected = prefixReference(values);
            for (int block : new int[]{1, 3, 7, 32, 128}) {
                assertSame(expected,
                        prefixBlocked(values, block));
                comparisons++;
            }
        }

        // 2000 scenarios * 4 block sizes = 8000 checks.
        for (int t = 0; t < 2000; t++) {
            int n = rng.nextInt(61);
            long[] values = new long[n];
            for (int i = 0; i < n; i++) {
                values[i] = rng.nextInt(-20, 21);
            }
            int width = rng.nextInt(1, n + 6);
            long[] expected = windowReference(
                    values, width);
            for (int block : new int[]{1, 2, 4, 12}) {
                assertSame(expected,
                        windowSumsBlocked(values, width, block));
                comparisons++;
            }
        }

        if (comparisons != 45000) {
            throw new AssertionError(
                    "Incorrect test count");
        }
        System.out.println(
                "Randomized reference checks: 45000 PASS");
    }

    public static void main(String[] args) {
        Matrix a = Matrix.fromRows(new long[][]{
                {1, 2, 3},
                {4, 5, 6}
        });
        Matrix b = Matrix.fromRows(new long[][]{
                {7, 8},
                {9, 10},
                {11, 12}
        });

        Matrix product = multiplyBlocked(a, b, 2);
        System.out.println(
                "Blocked multiply 2x3 x 3x2: "
                + Arrays.deepToString(product.toRows()));

        Matrix transposed = transposeBlocked(a, 2);
        System.out.println(
                "Blocked transpose 2x3: "
                + Arrays.deepToString(transposed.toRows()));

        long[] data = {3, -1, 4, -2, 5};
        System.out.println(
                "Blocked prefix B=2: "
                + Arrays.toString(prefixBlocked(data, 2)));
        System.out.println(
                "Blocked window W=3 B=2: "
                + Arrays.toString(
                        windowSumsBlocked(data, 3, 2)));

        Matrix zeroInner = multiplyBlocked(
                new Matrix(2, 0), new Matrix(0, 4), 3);
        long total = 0L;
        for (long x : zeroInner.data) {
            total = Math.addExact(total, x);
        }
        System.out.println(
                "Zero inner dimension: rows="
                + zeroInner.rows + ", cols=" + zeroInner.cols
                + ", entries=" + zeroInner.data.length
                + ", sum=" + total);

        Matrix emptyRows = transposeBlocked(
                new Matrix(0, 3), 5);
        System.out.println(
                "Zero-row transpose: rows="
                + emptyRows.rows + ", cols=" + emptyRows.cols
                + ", entries=" + emptyRows.data.length);

        boolean invalidShape = false;
        try {
            multiplyBlocked(
                    new Matrix(2, 3),
                    new Matrix(4, 2), 2);
        } catch (IllegalArgumentException expected) {
            invalidShape = true;
        }
        if (!invalidShape) {
            throw new AssertionError(
                    "Invalid shape was accepted");
        }
        System.out.println("Invalid shape: rejected");

        boolean invalidTile = false;
        try {
            transposeBlocked(a, 0);
        } catch (IllegalArgumentException expected) {
            invalidTile = true;
        }
        if (!invalidTile) {
            throw new AssertionError(
                    "Invalid block was accepted");
        }
        System.out.println("Invalid tile: rejected");

        randomChecks();
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -encoding UTF-8 BlockingMatrixArrayDemo.java
java BlockingMatrixArrayDemo
~~~

**Stdout chính xác:**

~~~text
Blocked multiply 2x3 x 3x2: [[58, 64], [139, 154]]
Blocked transpose 2x3: [[1, 4], [2, 5], [3, 6]]
Blocked prefix B=2: [3, 2, 6, 4, 9]
Blocked window W=3 B=2: [6, 1, 7]
Zero inner dimension: rows=2, cols=4, entries=8, sum=0
Zero-row transpose: rows=3, cols=0, entries=0
Invalid shape: rejected
Invalid tile: rejected
Randomized reference checks: 45000 PASS
~~~

### Giải thích từng dòng kết quả

**Blocked multiply:** ma trận A 2×3 và B 3×2 cho C 2×2 bằng [[58,64],[139,154]], gồm cả tile k cuối dài 1 khi block size=2.

**Blocked transpose:** chuyển vị A cho shape 3×2 và các hàng [1,4], [2,5], [3,6].

**Blocked prefix:** hai bước local prefix và carry trên dãy [3,−1,4,−2,5] trả đúng [3,2,6,4,9] dù khối cuối chỉ dài 1.

**Blocked window:** độ rộng 3, output tile size 2: cần halo để trả ba tổng cửa sổ [6,1,7]. Kết quả được tính lại bằng prefix **nội bộ từng tile**, không dùng prefix toàn dãy.

**Zero inner dimension:** nhân shape (2×0)·(0×4) hợp lệ và cho ma trận 2×4 có 8 số 0. Vì có một chiều p=0, không có phép nhân nào diễn ra.

**Zero-row transpose:** ma trận shape 0×3 có 0 phần tử, nhưng chuyển vị có shape **3×0** chứ không phải 0×0. Lưu shape tách với số phần tử giúp giữ ý nghĩa này.

**Invalid shape:** (2×3)·(4×2) không tương thích, ném IllegalArgumentException thay vì âm thầm sửa shape.

**Invalid tile:** block size 0 không hợp lệ; nếu cho 0, vòng `start=end` không tiến và có thể lặp vô hạn. Vì vậy phải từ chối ngay.

**Randomized reference checks:** 45.000 lượt so sánh gồm 10.000 lượt nhân ma trận, 12.000 chuyển vị, 15.000 tổng tiền tố và 8.000 cửa sổ. Chỉ in PASS khi mọi cặp kết quả **trùng chính xác** trên những dữ liệu nguyên nhỏ đã chọn.

## 20. Cách kiểm thử một thuật toán blocking

Blocking có nhiều vòng lặp chỉ số nên dễ mắc lỗi dù ý tưởng đúng. Để kiểm thử hiệu quả, nên có **thuật toán tham chiếu độc lập không blocking** và bao phủ nhiều ranh giới tile.

### Nhân ma trận

- Mạng kích thước m×p và p×n với m,p,n có thể bằng 0.
- Kích thước không chia hết block: 2×3 nhân 3×2 với b=2; 7×5 nhân 5×4 với b=3.
- Block nhỏ hơn, bằng, lớn hơn cả ma trận.
- Mảng gồm toàn số 0.
- Mảng có số âm, số dương và nhiều giá trị bằng nhau.
- Trường hợp một chiều rất nhỏ: 1×p nhân p×1.
- Trường hợp p=0, output zero.
- Shape không khớp phải ném lỗi.

Oracle: nhân i-j-k độc lập và so **mọi ô** cùng shape, không chỉ checksum.

### Chuyển vị

- Matrix chữ nhật 2×3 và 3×2.
- Shape 0×n và m×0.
- Mảng n=1, m=1.
- Tile cuối không đủ b.
- Chuyển vị **hai lần** phải khôi phục ma trận gốc, gồm cả shape.
- Input phải không bị thay đổi nếu API hứa out-of-place.

### Prefix theo khối

- Dãy rỗng và một phần tử.
- Toàn số âm.
- Xen kẽ dấu để kiểm carry âm/dương.
- Block size 1.
- Block size lớn hơn N.
- N không chia hết b.

Oracle: quét một lần giữ running sum.

### Window và halo

- w=1 (không có halo).
- w=N (chỉ một output).
- w>N (output rỗng).
- Tile output size 1.
- Tile output size lớn hơn số output.
- w lớn hơn tile output size, đảm bảo halo có thể dài hơn chính tile.
- Dãy tăng, giảm hoặc nhiều số âm.

Oracle: với mỗi output, cộng trực tiếp w phần tử. Nếu ranh giới sai, nó thường lộ ở tile đầu hoặc tile cuối.

### Bộ test độc lập đã chạy

Một mô hình kiểm thử riêng thực hiện:
- **12.000** ma trận nhân ngẫu nhiên chữ nhật, mỗi trường hợp so với phép nhân tham chiếu ở **6 block sizes** — **72.000 đối chiếu**.
- **15.000** ma trận chuyển vị ngẫu nhiên, so với vòng i-j ở **6 block sizes** — **90.000 đối chiếu**.
- **22.000** dãy prefix, mỗi dãy ở **7 block sizes** — **154.000 đối chiếu**.
- **18.000** dãy cửa sổ, mỗi dãy ở **6 block sizes** — **108.000 đối chiếu**.

Tổng **67.000 bộ dữ liệu** và **424.000 lượt đối chiếu độc lập**, tất cả khớp. Đây là kiểm thử tính đúng mô hình trên input nhỏ và vừa, **không chứng minh tính đúng bằng thử nghiệm trên mọi input** và **không đo mức tăng tốc cache/I/O**. Chứng minh phân hoạch bộ ba (i,k,j), công thức chuyển vị và phân rã prefix/halo mới là cơ sở lý thuyết.

## 21. Độ phức tạp chi tiết của bốn phương pháp

| Thuật toán | Phép toán chính | Bộ nhớ ngoài input/output | Điều kiện |
|---|---|---|---|
| Nhân ma trận chữ nhật blocked | **`O(mpn)`** | O(1) trong code in-memory không pack tile | Cần lưu A/B/C trong RAM |
| Chuyển vị ma trận blocked | **`O(mn)`** | O(1) ngoài output mới | Đọc/ghi theo tile |
| Prefix hai pha blocked | **`O(N)`** | **`O(⌈N/b⌉)`** block totals, ngoài output | Bảo toàn carry |
| Window sums theo block-local prefix | **`O(Q+⌈Q/b⌉·(w−1))`**, `Q=max(0,N−w+1)` | **`O(min(b,Q)+w)`** scratch, ngoài output | Đọc đủ halo |

**Phân biệt:** các công thức thời gian trên tính theo số bước thuật toán; **I/O complexity** trong mô hình ngoài RAM còn phụ thuộc cách tile được đọc và ghi thành block B. Chương trình Java không đo I/O cấp thiết bị và không dùng external files.

### Đánh đổi thời gian/bộ nhớ của window tiles

Nếu w lớn và b nhỏ, mỗi tile đọc lại w−1 halo và thuật toán có thể chậm hơn rolling sum một lượt. Có thể:
- Chọn b đủ lớn trong khả năng cache/RAM.
- Giữ lại overlap giữa các tile thay vì nạp lại.
- Dùng rolling sum nếu mục tiêu chỉ là tổng cửa sổ tuần tự.
- Dùng two-dimensional tiling/FFT/convolution chuyên dụng nếu bài toán là xử lý tín hiệu phức tạp.

Không chọn “blocked” chỉ vì nó có tên hấp dẫn; phải xem **phụ thuộc dữ liệu, tổng lượng I/O và throughput thật**.

## 22. Đánh giá hiệu năng mà không tự lừa mình

Một benchmark có ý nghĩa nên so các triển khai trên **cùng dữ liệu** và có kiểm chứng kết quả:

1. **Baseline**: thuật toán tham chiếu đúng, không blocked.
2. **Loop-reordered baseline**: ví dụ nhân i-k-j, giúp tách lợi ích do **đổi thứ tự vòng** khỏi lợi ích do **tiling**.
3. **Các tile size**: b=8,16,32,64,128 hoặc những giá trị phù hợp machine, cùng kích thước dữ liệu.
4. **Các shape**: vuông, rất cao/mỏng, rất rộng/thấp, bội số tile và không bội số.
5. **Các mức dữ liệu**: vừa L1/L2/LLC, vừa RAM nhưng vượt cache, lớn hơn RAM (nếu có xử lý file thực).
6. **Warm-up JVM/JIT**: chạy đủ trước khi đo để tránh kết luận từ compilation/cold start.
7. **Ngăn loại bỏ phép tính**: tiêu thụ checksum hoặc kiểm output sau khi chạy, tránh benchmark chỉ đo vòng lặp không có tác dụng.
8. **Nhiều lần chạy**: median/percentiles, sai số và thứ tự thực thi thay đổi để giảm tác động hệ thống.
9. **Ghi môi trường**: CPU, core count, heap size, GC, Java version, cache, SSD, file system, thread count.
10. **Đo riêng**: throughput phép nhân, cache misses (nếu có profiler), số page faults, bytes read/written, IOPS và latency khi out-of-core.

### Không dùng Stopwatch một lần cho kết luận “x nhanh gấp 20 lần”

Một lần chạy có thể bị ảnh hưởng bởi cold cache, GC, OS page cache, turbo boost, scheduler và quá trình khác. Với dữ liệu nhỏ, overhead `System.nanoTime()` và setup có thể chiếm phần đáng kể. Khi đo file I/O, phải nói rõ **cold-cache** hay **warm-cache**, và không tự gọi file lớn hơn RAM là benchmark “truy cập đĩa thật” nếu OS cache vẫn có thể giữ phần lớn dữ liệu.

### Phân biệt throughput và latency

Blocking có thể tăng **throughput** bằng cách xử lý nhiều item trong một batch, nhưng đôi khi tăng **latency** của item đầu tiên do đợi gom đủ block. Trong streaming thời gian thực, có thể cần block nhỏ hơn hoặc cơ chế flush theo thời gian.

## 23. Tránh dữ liệu bị ghi đè hoặc aliasing

Một tối ưu bằng tile có thể vô tình ghi ra vùng đang được phép tính khác sử dụng:

- **Matrix multiplication:** nếu C trùng data array với A hoặc B, các cập nhật của C có thể phá dữ liệu đầu vào chưa được đọc; cần output riêng hoặc thuật toán in-place có chứng minh cụ thể.
- **Transpose:** với output riêng thì đơn giản; in-place rectangular transpose cần quản lý hoán vị index hoặc buffer phụ.
- **Prefix:** nếu output dùng cùng array với input, hai pha phải phân tích xem dữ liệu gốc còn cần cho các block khác hay không. Mã demo chọn output mới, không chấp nhận aliasing.
- **Stencil:** đọc dữ liệu “thời điểm trước” và ghi “thời điểm sau” cần double buffering hoặc lịch phù hợp.
- **Parallel blocks:** mỗi worker nên ghi một vùng output riêng hoặc dùng đồng bộ nếu có phần overlap thật sự.

Nếu hai worker cùng ghi một ô C[i,j] khi nhân tile theo k0 khác nhau, sẽ có **data race**. Một cách chia song song an toàn là mỗi worker sở hữu một **tile output C riêng**, và cộng tuần tự các k tile trong worker đó; hoặc dùng reduction có đồng bộ đã thiết kế.

## 24. Chặn khối và xử lý ngoài bộ nhớ trên Java

### Khi dùng stream/file

Một pipeline ngoài RAM có thể:
- Đọc input theo một buffer ByteBuffer hữu hạn, không gọi `Files.readAllBytes` cho file rất lớn.
- Định nghĩa rõ `blockBytes` và số phần tử `elementCount`.
- Decode dữ liệu theo endianness đúng; kiểm số byte thực tế đọc.
- Xử lý trong RAM rồi ghi kết quả theo buffer.
- Giữ một **carry** giữa các block với prefix/scan.
- Giữ **halo** ở biên các block đối với cửa sổ/stencil.
- Cân nhắc direct buffer/off-heap khi đo thấy có lợi, nhưng kiểm dung lượng bộ nhớ ngoài heap và GC.
- Ghi metadata để khôi phục shape, dimensions và index.

### Short reads và short writes

Với Java `FileChannel.read(ByteBuffer)` hoặc `write(ByteBuffer)`, một lần gọi **không luôn đảm bảo** đã đọc/ghi hết toàn bộ buffer được yêu cầu. Code thực tế cần vòng lặp cho tới khi đủ byte hoặc gặp EOF/lỗi theo hợp đồng.

Một tile được yêu cầu 32 KiB nhưng chỉ nhận 16 KiB không thể coi như “tile cuối” nếu file còn dữ liệu và short read chỉ là tình huống tạm thời. Phải phân biệt **end-of-file thực** với **đọc chưa đủ**.

### Định dạng file và shape

Nếu file lưu long row-major:
- Địa chỉ byte của phần tử A[i,j] theo data offset có dạng `base+8·(i·cols+j)`, với dữ liệu little/big endian được quy định.
- Cần kiểm offset nhân không overflow long.
- Khi đọc tile hình chữ nhật, không được nhầm b hàng mỗi hàng b phần tử với một đoạn b² liên tiếp.
- Nếu có compression, một random tile có thể phải giải nén cả block nén; layout lại ảnh hưởng mạnh đến chi phí.

### Dữ liệu thực không vừa RAM

Nếu A/B/C trên heap cộng lại vượt RAM, hệ thống có thể rơi vào paging liên tục, GC pressure hoặc lỗi cấp phát. Đó **không phải** một chiến lược out-of-core hiệu quả. Cần chủ động giới hạn buffer/heap và quản lý file tiles như mục 9.

## 25. Lựa chọn b theo đặc điểm xử lý

### Bài ma trận rất nhỏ

Nếu mọi thứ vừa L1, thêm nhiều lớp for tile có thể làm code chậm hơn. Cần benchmark trên kích thước thật; đôi khi loop i-k-j hoặc thư viện tối ưu đã đủ.

### Bài ma trận lớn trên CPU

Xét:
- Packed panels.
- Vectorization.
- Multi-level blocking theo L1/L2/LLC.
- Khởi tạo/giữ accumulator C trong registers hoặc tile nhỏ.
- Tối ưu b_i,b_j,b_k riêng.
- Chia output tiles cho các thread để tránh ghi đè.
- BLAS/Java Vector API/native library khi phù hợp và được phép.

### Bài ngoài RAM

Xét:
- RAM ngân sách để chứa tile và buffer.
- Block I/O B, kích thước page/stripe.
- File layout tiled hay row-major.
- Số lần phải đọc A/B panel.
- Giữ C tile xuyên các k blocks.
- Số IOPS do đọc nhiều đoạn nhỏ; latency.
- Double buffering và async I/O.
- Checkpoint/resume cho job dài.

### Dãy có phụ thuộc cục bộ

Nếu mỗi output cần w item liên tiếp, kích thước input tile là outputTile+w−1. Tăng b giúp giảm tỷ lệ overhead halo:

**`overheadFraction≈(w−1)/b`** cho tile đầy.

Nhưng b lớn tốn buffer hơn và có thể vượt cache. Nếu w≫b, thuật toán window tile với halo lặp lại nhiều dữ liệu; cân nhắc rolling computation hoặc giữ overlap.

## 26. Những lỗi thường gặp

1. **Nhầm cache tiling trên ba mảng RAM với thuật toán ngoài bộ nhớ thực sự**.
2. **Nói blocking giảm nhân ma trận O(n³) xuống O(n²)** chỉ vì ít cache misses.
3. **Quên cộng dồn C qua mọi k tile**; ghi đè C sau mỗi k block.
4. **Chỉ chạy floor(N/b) tile**, bỏ khối cuối không đầy.
5. **Tự cộng b vào start mà không xét overflow int** ở kích thước rất lớn.
6. **Dùng sai shape m×p·p×n** hoặc không kiểm inner dimensions.
7. **Chỉ test m=p=n chia hết b**, bỏ lỗi chữ nhật và biên.
8. **Nhầm row-major index i·cols+j với j·rows+i** ở ma trận không chuyển vị.
9. **Dùng cùng một index công thức cho A và Aᵀ** khiến transpose sai.
10. **Chuyển vị in-place rectangular bằng cách chỉ đổi metadata** mà không đổi array.
11. **Cho C alias với A/B khi nhân**, phá phần tử chưa đọc.
12. **Bỏ qua khả năng dữ liệu B/C truy cập stride lớn** khi chỉ đổi loop bên ngoài.
13. **Lựa chọn b bằng cảm giác**, không xét working set/cache/page.
14. **Chọn b sao cho 3b²s bằng toàn bộ cache** và không chừa không gian cho dữ liệu khác.
15. **Nghĩ tile b×b luôn liên tục trong file row-major**, trong khi gồm nhiều đoạn hàng.
16. **Đọc một tile từ file chỉ bằng một read(b²)** khi layout không tiled.
17. **Không phân biệt page size B và tile dimension b**, dùng sai đơn vị.
18. **Đếm phép cộng CPU thay cho số block I/O** khi phân tích external-memory.
19. **Cho mỗi lần FileChannel.read phải trả đủ requested bytes**.
20. **Không kiểm EOF, short read/write và endianness** khi đọc file binary.
21. **Coi memory mapping tự động tối ưu locality** bất kể access pattern.
22. **Không lưu shape khi dữ liệu có chiều 0**, làm mất thông tin 0×n hay m×0.
23. **Bỏ qua overflow rows·cols** và cấp phát mảng kích thước âm.
24. **Dùng int cho tổng tích rất lớn**, tạo overflow âm thầm.
25. **Dùng Math.addExact nhưng tuyên bố có rollback atomic** sau ngoại lệ.
26. **Dùng double mà bắt kết quả blocked bằng exact bits của baseline** trên mọi input.
27. **Đổi thứ tự các phép toán có phụ thuộc hoặc không kết hợp** mà không phân tích.
28. **Chặn khối prefix nhưng không cộng carry của các khối trước**.
29. **Cộng carry sau khi đã cập nhật blockTotal bằng prefix toàn cục**, vô tình cộng lặp.
30. **Không reset local running khi bắt đầu khối prefix mới** trong phương pháp hai pha.
31. **Cho hai pha prefix luôn nhanh hơn streaming một lượt**.
32. **Tính cửa sổ ở biên tile nhưng không nạp halo**.
33. **Đọc halo theo w thay vì w−1**, có thể thừa một vị trí hoặc vượt mảng.
34. **Kết thúc input tile ở end+w thay vì end+w−1** trong đoạn nửa mở.
35. **Chỉ test window w nhỏ hơn tile**, bỏ ca halo lớn hơn tile.
36. **Không tính lại halo overhead khi b rất nhỏ/w rất lớn**.
37. **Cho blocked window luôn O(N)** bất kể b,w**, dù có tái đọc nhiều halo.
38. **Gọi một out-of-core scan O(N/B) phép toán CPU** — chỉ là số block I/O lý tưởng.
39. **Không xét tile reads qua nhiều hàng gây seek** khi lưu file row-major.
40. **Cho buffer tile b² đủ cho cả A/B/C và metadata**, bỏ chi phí phụ.
41. **Chia output C theo k block giữa các thread mà không đồng bộ**, tạo race.
42. **Cho worker stencil ghi đè input của worker khác**, sai phụ thuộc thời gian.
43. **Không tính chi phí đóng gói/giải nén tile**, benchmark thiếu phần đáng kể.
44. **Benchmark một lần không warm-up JVM**, kết luận tốc độ thiếu đáng tin.
45. **So cold-cache baseline với warm-cache blocked**, đo không công bằng.
46. **So checksum mà không so shape/nội dung**, bỏ bug hoán vị chỉ số.
47. **Tưởng O(1) scratch của in-memory tiled đồng nghĩa O(1) RAM tổng**, quên A/B/C vẫn ở heap.
48. **Bỏ qua local buffer + output allocation của window/prefix**.
49. **Chọn b lớn hơn dữ liệu và tin rằng luôn tăng tốc**.
50. **Tự áp cận I/O n³/(B√M) vào mọi nhân ma trận và mọi thuật toán**, không nêu giả thiết.
51. **Không kiểm trường hợp p=0 khi nhân**, trả shape sai hoặc truy cập không tồn tại.
52. **Không kiểm tile size 0/âm**, có thể gây vòng lặp không tiến.
53. **Không xác định input toàn bộ có fit RAM hay không**, chọn sai kiến trúc.
54. **Không phân biệt throughput với latency** khi dùng blocking trong streaming.
55. **Không đo bytes read/written/IOPS khi mục tiêu là tối ưu ngoài bộ nhớ**.
56. **Không giữ ownership của output tile khi đa luồng**, tạo false sharing hoặc data race.
57. **Sử dụng buffered stream nhưng vẫn gọi read() từng phần tử không cần thiết**, overhead lớn.
58. **Cho rằng nhiều block nhỏ luôn tốt** mà bỏ overhead scheduling/file I/O.
59. **Không dùng thuật toán oracle khác cấu trúc**, có thể lặp cùng bug.
60. **Tuyên bố speedup từ phép đếm mà chưa benchmark trên thiết bị thật**.

## 27. Bài tập tự luyện

**Bài 1 — Stride row-major.** Với `long[]` mô tả ma trận 1024×4096, tính chênh lệch byte của hai ô kề hàng và hai ô kề cột. Vì sao duyệt theo hàng có lợi?

**Bài 2 — Loop order.** Viết nhân ma trận i-j-k và i-k-j. So sánh những phần tử A/B/C được đọc liên tục trong hai cách.

**Bài 3 — Tile multiply.** Với A 2×3 và B 3×2 ở mục 6, tile=2, ghi đóng góp vào C sau k tile [0,2) rồi sau [2,3). Kiểm [[58,64],[139,154]].

**Bài 4 — Rectangular.** Tạo A 7×5, B 5×4, chọn b=3, liệt kê tất cả i0/k0/j0 và độ dài tile cuối.

**Bài 5 — Identity zero inner.** Tính shape/kết quả của (2×0)·(0×4) và chuyển vị 0×3. Vì sao chỉ lưu data.length không đủ để suy shape?

**Bài 6 — Chuyển vị.** Với A 2×3, tự tính index của A[1,2] và T[2,1] trong hai mảng flat row-major. Kiểm cùng giá trị 6.

**Bài 7 — RAM budget.** Với bộ nhớ cache ngân sách 48 KiB, phần tử double 8 byte, ước lượng b lớn nhất sao cho ba tile b×b chiếm không quá 70% ngân sách. Tại sao b tính được chỉ là điểm bắt đầu benchmark?

**Bài 8 — I/O scan.** Với N=10⁸ phần tử và một I/O block B=4096 phần tử, tính số block lý tưởng cho một lượt quét và phân biệt với số phép toán CPU.

**Bài 9 — Out-of-core.** Giả sử A/B/C không vừa RAM, chỉ có RAM cho ba tile b×b. Viết pseudocode đọc tile và ghi Ctile sau khi cộng đủ k blocks.

**Bài 10 — File layout.** Chứng minh tile 4×4 trong ma trận row-major 1000 cột không phải một đoạn 16 phần tử liên tiếp, trừ khi format file được tile hóa.

**Bài 11 — Prefix.** Chia [3,−1,4,−2,5] thành tile b=2, tính local prefix, blockTotal và carry rồi ghép thành [3,2,6,4,9].

**Bài 12 — Window halo.** Với N=10,w=4,outputTile=3, liệt kê mỗi block output [s,e) và input [s,e+w−1). Đếm số lần dữ liệu input bị đọc nếu không giữ overlap.

**Bài 13 — Stencil 2D.** Với kernel 5×5, bán kính r=2 và output tile 32×32, ước lượng kích thước vùng input cần đọc cho tile ở giữa ảnh.

**Bài 14 — Alias.** Cho ví dụ nhân ma trận C cùng array với A làm output sai vì một phần tử A bị ghi đè trước khi dùng xong.

**Bài 15 — Overflow.** Nếu mỗi phần tử có trị tuyệt đối 10⁹ và p=10⁵, ước lượng cận tổng độ lớn một ô C và kiểm long có đủ không.

**Bài 16 — Floating point.** Tạo ma trận có các số rất lớn/nhỏ đối dấu, so i-j-k với blocked trên double. Vì sao kết quả có thể khác một vài bit?

**Bài 17 — Benchmark.** Đo nhiều lần b∈{8,16,32,64} trên ma trận 64×64, 512×512 và 2048×2048, có warm-up và output validation. Ghi thời gian median, throughput và heap usage.

**Bài 18 — Parallel tiles.** Thiết kế phân chia theo output Ctile cho nhiều thread để không có hai thread cùng ghi một ô C.

**Bài 19 — Nâng cấp ra file.** Thiết kế cách đọc tile row-major bằng FileChannel, ghi rõ offsets/short reads/endianness và kiểm đúng trên một file test nhỏ.

**Bài 20 — Halo overhead.** So chi phí blocked window với rolling sum khi w=1000,b=32 và khi w=3,b=1024. Trường hợp nào hợp lý để giữ overlapping input giữa các tile?

## 28. Checklist chọn blocking trong thực tế

- Đã xác định chính xác **đơn vị đo khối** (elements, byte, cache line, page)?
- Có biết mảng/ma trận lưu **row-major, column-major hay tiled**?
- Đã tính **stride** của các truy cập nóng?
- Đã phân biệt **cache tiling trên RAM** với **out-of-core file processing**?
- Có biết ngân sách memory M và I/O block B trong mô hình đang dùng?
- Cần giữ A/B/C tile hoặc input/output/halo trong RAM đến bao giờ?
- Đã chọn tile size sao cho working set vừa cache/buffer mà vẫn có headroom?
- Nếu nhân ma trận, có cộng dồn đủ **mọi k tile** vào C?
- Có đảm bảo một bộ ba (i,k,j) được xét đúng một lần?
- Có hỗ trợ shape ma trận **chữ nhật** và chiều bằng 0?
- Có xử lý khối cuối bằng min thay vì bỏ hoặc truy cập vượt biên?
- Có khởi tạo C đúng và tránh aliasing với A/B?
- Nếu chuyển vị, có dùng index `j·m+i` cho output?
- Nếu prefix theo khối, đã ghép carry từ **tất cả khối trước**?
- Nếu window/stencil, có đọc đủ **halo** và định nghĩa biên?
- Có tính overhead đọc lại halo theo w và b?
- Có đủ kiểu số và chính sách overflow/precision?
- Nếu dữ liệu ngoài RAM, đã có **readTile/writeTile thực** và file layout phù hợp?
- Đã xử lý short reads/writes, EOF, alignment, endian và lỗi I/O?
- Có tránh race nếu các worker xử lý tile song song?
- Có oracle không blocked để so **toàn bộ output**?
- Có test b=1, b>dimensions, n=0, n=1, mọi tile cuối và width>N?
- Có benchmark đúng warm-up, nhiều lần, cùng input và có validation?
- Có đo cache/I/O khi mục tiêu là giảm transfer thay vì chỉ đếm phép cộng?
- Có chọn đơn giản hơn (loop reorder, rolling sum, streaming carry) khi nó đã tốt?

**Kết luận:** chặn khối là một kỹ thuật **tổ chức lại truy cập dữ liệu**, không phải một công thức làm giảm số phép nhân/cộng của bài toán. Với ma trận, loop tiling cải thiện cơ hội tái sử dụng A/B/C trong cache; chuyển vị theo tile hạn chế vùng đọc/ghi có stride; với dãy, **prefix phải có carry giữa các khối**, còn cửa sổ/stencil phải có **halo** ở biên. Khi dữ liệu thực sự vượt RAM, cần một kiến trúc **đọc/ghi tile từ file** và phân tích số chuyển block B với ngân sách RAM M; một chương trình chỉ dùng `long[]` trên heap mới là **in-memory cache blocking**. Thiết kế tốt phải giữ đúng shape, thứ tự tính toán, biên và số học, sau đó mới chọn b theo phần cứng và benchmark bằng kết quả đã được đối chiếu với một oracle độc lập.