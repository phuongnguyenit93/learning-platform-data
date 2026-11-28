# Ma trận thưa bằng bộ ba tọa độ, CSR và CSC

## 1. Khi nào cần biểu diễn ma trận thưa?

Một ma trận kích thước `m × n` có `m × n` ô. Nếu hầu hết ô bằng `0`, lưu tất cả ô trong mảng hai chiều sẽ tốn bộ nhớ cho cả những giá trị không mang thông tin. **Ma trận thưa (sparse matrix)** chỉ lưu các phần tử khác 0 cùng thông tin xác định vị trí của chúng.

Ví dụ, ma trận `A` có 4 hàng, 5 cột:

\[
A=
\begin{bmatrix}
0 & 0 & 0 & 7 & 0\\
5 & 0 & 0 & 0 & -2\\
0 & 0 & 0 & 0 & 0\\
0 & 4 & 0 & 0 & 9
\end{bmatrix}
\]

Trong 20 ô, chỉ có 5 phần tử khác 0. Gọi `nnz` là số *nonzero* được lưu theo một quy tắc chuẩn hóa nhất quán:

\[
m=4,\quad n=5,\quad nnz=5,\quad
\text{density}=\frac{nnz}{mn}=\frac{5}{20}=25\%.
\]

Dòng thứ ba (chỉ số `2` nếu đếm từ `0`) và cột thứ ba (chỉ số `2`) đều rỗng. Đây là ví dụ hữu ích vì biểu diễn nén phải ghi nhận chính xác cả **hàng/cột không có phần tử nào được lưu**.

Ba cách phổ biến trong chủ đề **Biểu diễn gọn** là:

- **COO (Coordinate format):** mỗi phần tử được lưu dưới dạng bộ ba tọa độ `(row, col, value)`.
- **CSR (Compressed Sparse Row):** nhóm các phần tử theo **hàng**, dùng mảng con trỏ để xác định đoạn của mỗi hàng.
- **CSC (Compressed Sparse Column):** nhóm các phần tử theo **cột**, dùng mảng con trỏ để xác định đoạn của mỗi cột.

Đây là những cách tổ chức dữ liệu khác nhau cho cùng một ma trận, phù hợp với các bài toán trong đồ thị, hệ phương trình tuyến tính, tìm kiếm thông tin, học máy và tính toán khoa học. Việc chọn COO, CSR hay CSC gắn trực tiếp với mục tiêu của học phần cấu trúc dữ liệu: hiểu **bất biến biểu diễn, thao tác và độ phức tạp thời gian/bộ nhớ** trước khi chọn cách lưu trữ.

Sau bài học, bạn cần tự tạo được ba biểu diễn cho một ma trận, đọc đúng các mảng con trỏ, chuyển đổi giữa chúng, thực hiện phép nhân ma trận–vector và nhận ra các trường hợp dễ mắc lỗi.

## 2. Quy ước trước khi lưu ma trận

Trong bài này, mọi chỉ số bắt đầu từ `0`:

- `0 ≤ row < m` và `0 ≤ col < n`.
- `A[row, col] = 0` nếu tọa độ đó không có phần tử được lưu.
- `nnz` là số cặp tọa độ **khác nhau** có giá trị khác `0` trong biểu diễn chuẩn hóa.
- Một ô được lưu nhiều lần trong dữ liệu nhập phải được xử lý bằng **quy tắc rõ ràng**. Trong ví dụ này, ta **cộng các giá trị có cùng tọa độ**, rồi loại ô nếu tổng bằng `0`.
- Các ví dụ dùng số thực hữu hạn. Một ứng dụng thực tế có thể cần quy tắc riêng cho `NaN`, vô cực, số phức, số rất nhỏ hoặc những giá trị được xem là “zero” theo ngưỡng.

Ví dụ danh sách nhập có thể chứa:

```text
(1, 4, -1)
(1, 4, -1)  -> sau khi gộp thành (1, 4, -2)

(2, 2,  3)
(2, 2, -3)  -> tổng bằng 0, không lưu trong bản chuẩn hóa
```

**Không phải mọi thư viện đều mặc định cộng tọa độ trùng.** Một số định dạng có thể tạm chấp nhận mục trùng trước khi canonicalize, hoặc có quy tắc ghi đè. Trước khi chuyển đổi và so sánh số lượng `nnz`, cần xác định hợp đồng dữ liệu nhập.

Cũng cần phân biệt **zero ngầm định** với **dữ liệu thiếu**: trong ma trận thưa toán học ở đây, ô không được lưu mang giá trị `0`; nếu bài toán của bạn có giá trị `missing`/`null` thì không thể tự động đồng nhất nó với `0`.

## 3. COO: lưu các bộ ba tọa độ

### 3.1. Cấu trúc

COO lưu ba mảng có cùng độ dài `nnz`:

```text
rows   = [0, 1, 1, 3, 3]
cols   = [3, 0, 4, 1, 4]
values = [7, 5,-2, 4, 9]
```

Phần tử thứ `k` của cả ba mảng mô tả một ô:

\[
A[\text{rows}[k],\text{cols}[k]]=\text{values}[k].
\]

Với dữ liệu trên:

| `k` | `rows[k]` | `cols[k]` | `values[k]` | Ô tương ứng |
|---:|---:|---:|---:|---|
| 0 | 0 | 3 | 7 | `A[0,3] = 7` |
| 1 | 1 | 0 | 5 | `A[1,0] = 5` |
| 2 | 1 | 4 | −2 | `A[1,4] = −2` |
| 3 | 3 | 1 | 4 | `A[3,1] = 4` |
| 4 | 3 | 4 | 9 | `A[3,4] = 9` |

COO **không bắt buộc phải sắp xếp** trong mọi API; có thể thêm một bộ ba vào cuối một danh sách ngay khi gặp dữ liệu mới. Để chuyển đổi và tra cứu dễ dàng, ta thường tạo **COO chuẩn hóa**: các tọa độ duy nhất, không lưu giá trị `0`, sắp theo `row` rồi `col` tăng dần.

### 3.2. Ưu điểm và hạn chế

COO phù hợp cho giai đoạn **thu thập hoặc xây dựng ma trận**: một vòng lặp đọc dữ liệu chỉ cần thêm các bộ ba. Nếu các danh sách dùng mảng động, thêm ở cuối có chi phí `O(1)` khấu hao mỗi mục (chưa tính gộp trùng).

Nhược điểm là đọc toàn bộ một hàng hoặc một cột phải dò các tọa độ, thường `O(nnz)` nếu COO không có chỉ mục. Với COO chuẩn hóa, tìm một ô có thể dùng tìm kiếm nhị phân trên cặp `(row, col)` trong `O(log nnz)`, nhưng các thao tác duyệt hàng liên tiếp vẫn phải xác định đoạn thích hợp.

COO cũng lưu **hai chỉ số cho mỗi giá trị**. Nếu nhiều phần tử cùng hàng, việc lặp lại chỉ số hàng gây lãng phí; CSR giải quyết điều đó bằng cách mã hóa vị trí bắt đầu của từng hàng.

## 4. CSR: nén theo hàng

### 4.1. Ba mảng của CSR

**CSR (Compressed Sparse Row)** dùng:

1. `values`: giá trị của các phần tử khác 0, sắp theo từng hàng.
2. `colIdx`: chỉ số cột của từng phần tử tương ứng trong `values`.
3. `rowPtr`: mảng độ dài `m + 1`; `rowPtr[r]` là chỉ số bắt đầu các phần tử của hàng `r` trong `values`.

Với ma trận `A`:

```text
values = [7, 5, -2, 4, 9]
colIdx = [3, 0,  4, 1, 4]
rowPtr = [0, 1,  3, 3, 5]
         r0 r1  r2 r3 end
```

Các phần tử của hàng `r` nằm trong đoạn **nửa mở**:

\[
k\in[\text{rowPtr}[r],\ \text{rowPtr}[r+1]).
\]

Do đó:

| Hàng `r` | `rowPtr[r]` | `rowPtr[r+1]` | Các mục `(col, value)` |
|---:|---:|---:|---|
| 0 | 0 | 1 | `(3, 7)` |
| 1 | 1 | 3 | `(0, 5), (4, −2)` |
| 2 | 3 | 3 | **Rỗng** |
| 3 | 3 | 5 | `(1, 4), (4, 9)` |

Ở hàng `2`, `rowPtr[2] = rowPtr[3] = 3`. Hai con trỏ bằng nhau là cách chính xác để biểu diễn hàng rỗng; **không cần lưu một giá trị 0 giả** vào `values`.

Số phần tử của hàng `r` là:

\[
nnz_r=\text{rowPtr}[r+1]-\text{rowPtr}[r].
\]

### 4.2. Bất biến cần giữ đúng

Một CSR hợp lệ phải thỏa mãn:

- `rowPtr.length = m + 1`; `values.length = colIdx.length = nnz`.
- `rowPtr[0] = 0` và `rowPtr[m] = nnz`.
- `0 ≤ rowPtr[r] ≤ rowPtr[r+1] ≤ nnz` cho mọi hàng.
- Mọi `colIdx[k]` nằm trong `[0, n)`.
- Mỗi đoạn hàng chứa đúng các phần tử thuộc hàng đó.
- Nếu chọn biểu diễn **canonical**, chỉ số cột trong từng hàng tăng nghiêm ngặt và không có tọa độ lặp hoặc giá trị bằng `0`.

Tính tăng nghiêm ngặt của `colIdx` **không phải yêu cầu của mọi cách lưu CSR**; nhiều thư viện hỗ trợ đoạn hàng chưa sắp hoặc có mục trùng để xây dựng nhanh. Tuy nhiên, tìm kiếm nhị phân và một số thuật toán tối ưu cần dạng đã sắp và gộp trùng.

### 4.3. Truy cập và thao tác

Để đọc hàng `r`, chỉ cần lấy `start = rowPtr[r]`, `end = rowPtr[r+1]` và duyệt `k = start ... end-1`. Chi phí là `O(1 + nnz_r)`, trong đó `nnz_r` là số phần tử được lưu trên hàng.

Để lấy `A[r,c]` khi cột trong hàng đã được sắp, tìm nhị phân `c` trong đoạn hàng: `O(log(1+nnz_r))`; nếu không tìm thấy thì trả `0`. Với đoạn chưa sắp, thường cần quét `O(nnz_r)`.

CSR hữu ích cho **nhân ma trận–vector**, duyệt các hàng độc lập, lấy tổng/hàm gộp theo hàng và các thuật toán trên danh sách đỉnh kề theo hàng. Nhưng **chèn một phần tử mới** vào giữa `values` có thể phải dời nhiều mục và tăng các con trỏ của các hàng sau, nên không phù hợp cho rất nhiều lần chèn/xóa cấu trúc liên tục.

## 5. CSC: nén theo cột

**CSC (Compressed Sparse Column)** là hình ảnh đối xứng của CSR khi đổi vai trò hàng và cột. Ba mảng:

- `values`: các giá trị sắp theo cột.
- `rowIdx`: chỉ số hàng của các giá trị.
- `colPtr`: mảng dài `n + 1`; phần tử cột `c` nằm trong đoạn `[colPtr[c], colPtr[c+1])`.

Ma trận `A` ở trên có:

```text
values = [5, 4, 7, -2, 9]
rowIdx = [1, 3, 0,  1, 3]
colPtr = [0, 1, 2,  2, 3, 5]
         c0 c1 c2  c3 c4 end
```

Lần theo từng cột:

| Cột `c` | Đoạn `[colPtr[c], colPtr[c+1])` | Các mục `(row, value)` |
|---:|---|---|
| 0 | `[0,1)` | `(1,5)` |
| 1 | `[1,2)` | `(3,4)` |
| 2 | `[2,2)` | **Rỗng** |
| 3 | `[2,3)` | `(0,7)` |
| 4 | `[3,5)` | `(1,−2), (3,9)` |

Giống CSR, CSC có các bất biến:

\[
\begin{aligned}
&\text{colPtr.length}=n+1,\quad
\text{colPtr}[0]=0,\quad \text{colPtr}[n]=nnz,\\
&0\le \text{colPtr}[c]\le \text{colPtr}[c+1]\le nnz.
\end{aligned}
\]

Mỗi `rowIdx[k]` nằm trong `[0,m)`. Nếu CSC canonical, các chỉ số hàng **tăng nghiêm ngặt trong từng cột**. Khi đó, lấy `A[r,c]` bằng tìm kiếm nhị phân trong đoạn cột mất `O(log(1+nnz_c))`.

CSC thuận lợi khi thuật toán làm việc **theo cột**: lấy vector cột, tổng hợp đặc trưng theo cột, một số phép toán đại số tuyến tính và bộ giải hệ phương trình thưa. Việc duyệt một hàng rải rác qua nhiều cột sẽ kém tự nhiên hơn so với CSR.

### 5.1. Đừng nhầm đổi thứ tự với chuyển vị

CSR và CSC của **cùng ma trận `A`** thường lưu các giá trị theo thứ tự khác nhau. Trong ví dụ:

```text
CSR(A).values = [7,5,-2,4,9]
CSC(A).values = [5,4,7,-2,9]
```

Chỉ đổi tên `rowPtr` thành `colPtr` mà giữ nguyên `values` sẽ **không tạo ra CSC(A)** hợp lệ. Phải sắp lại giá trị và chỉ số theo cột, hoặc dùng thuật toán phân phối tuyến tính.

Ngược lại, **CSC(A)** có thể được **diễn giải như CSR(Aᵀ)**, bằng cách đổi kích thước `m×n` thành `n×m` và dùng:

```text
CSR(Aᵀ).rowPtr = CSC(A).colPtr
CSR(Aᵀ).colIdx = CSC(A).rowIdx
CSR(Aᵀ).values = CSC(A).values
```

Việc diễn giải lại này có thể mất `O(1)` cho metadata và chia sẻ các mảng, **nếu dữ liệu được coi bất biến**. Muốn hai ma trận có thể sửa độc lập phải xử lý quyền sở hữu hoặc sao chép dữ liệu tương ứng.

## 6. Xây dựng CSR và CSC từ COO

### 6.1. Chuẩn hóa trước khi chuyển đổi

Một quy trình rõ ràng:

1. Kiểm tra kích thước `m,n` và mọi tọa độ hợp lệ.
2. Quyết định quy tắc xử lý các mục trùng (`sum`, ghi đè hoặc giữ mục trùng tùy bài toán).
3. Gộp các tọa độ theo quy tắc đã chọn và loại các tổng bằng `0`, nếu dùng dạng canonical.
4. Sắp các mục theo `(row,col)` cho COO canonical.
5. Chuyển thành CSR hoặc CSC.

Nếu đã có COO canonical theo hàng, lấy `values` và `colIdx` của CSR từ danh sách đó, còn `rowPtr` được tạo bằng **đếm số mục từng hàng rồi cộng dồn**.

Ví dụ, số mục mỗi hàng là `[1,2,0,2]`. Khởi tạo `rowPtr[0]=0`, lần lượt cộng số mục:

```text
rowCounts = [1,2,0,2]

rowPtr[0] = 0
rowPtr[1] = rowPtr[0] + 1 = 1
rowPtr[2] = rowPtr[1] + 2 = 3
rowPtr[3] = rowPtr[2] + 0 = 3
rowPtr[4] = rowPtr[3] + 2 = 5

=> rowPtr = [0,1,3,3,5]
```

Với CSC, cần gom theo cột. Đếm `colCounts = [1,1,0,1,2]` rồi cộng dồn được:

```text
colPtr = [0,1,2,2,3,5]
```

Sau đó, đặt từng bộ ba vào **vị trí tiếp theo của cột tương ứng**. Nếu duyệt COO canonical theo hàng từ nhỏ tới lớn, các `rowIdx` trong mỗi cột cũng tăng theo hàng; ta nhận được CSC đã sắp theo hàng mà không cần sort lại.

### 6.2. Thuật toán cộng dồn và phân phối

Với một danh sách bộ ba có tọa độ hợp lệ và **đã chuẩn hóa**, các bước đếm và phân phối có thể làm trong:

- `O(m+nnz)` để xây CSR khi các mục COO đã theo thứ tự hàng.
- `O(n+nnz)` để xây CSC bằng cách đếm theo cột, tính prefix sum rồi phân phối các mục vào cột.

Nếu COO chưa sắp, có thể dùng đếm/phân phối để nhóm theo hàng hoặc cột trong cùng độ phức tạp trên, nhưng **thứ tự phụ bên trong mỗi hàng/cột có thể chưa tăng**. Sắp COO bằng phép sort so sánh thông thường tốn `O(nnz \log nnz)`; xử lý trùng bằng sort và gộp có độ phức tạp tương tự. Cũng có cách gộp bằng bảng băm với chi phí trung bình tuyến tính, đổi lại quản lý hash và lựa chọn thứ tự xuất ra.

## 7. Ví dụ TypeScript đầy đủ: COO → CSR/CSC và nhân vector

Mã dưới đây sử dụng các mảng số JavaScript cho dễ hiểu, chỉ nhận giá trị hữu hạn, đánh chỉ số từ `0` và **gộp trùng bằng phép cộng**. Đầu vào được chuẩn hóa để loại `0` và sắp theo hàng/cột. Bản triển khai dành cho mục đích học tập; hệ thống lớn thường dùng `Int32Array` hoặc `Uint32Array`, `Float32Array`/`Float64Array`, thư viện toán học tối ưu và cơ chế kiểm tra tràn chỉ số.

```ts
type Entry = Readonly<{
  row: number;
  col: number;
  value: number;
}>;

type COO = Readonly<{
  rows: number;
  cols: number;
  entries: readonly Entry[];
}>;

type CSR = Readonly<{
  rows: number;
  cols: number;
  rowPtr: readonly number[];
  colIdx: readonly number[];
  values: readonly number[];
}>;

type CSC = Readonly<{
  rows: number;
  cols: number;
  colPtr: readonly number[];
  rowIdx: readonly number[];
  values: readonly number[];
}>;

function makeCOO(
  rows: number,
  cols: number,
  source: readonly Entry[]
): COO {
  if (
    !Number.isSafeInteger(rows) || rows < 0 ||
    !Number.isSafeInteger(cols) || cols < 0
  ) {
    throw new RangeError("Kích thước ma trận không hợp lệ");
  }

  const sorted: Entry[] = [];
  for (const e of source) {
    if (
      !Number.isSafeInteger(e.row) ||
      !Number.isSafeInteger(e.col) ||
      e.row < 0 || e.row >= rows ||
      e.col < 0 || e.col >= cols
    ) {
      throw new RangeError("Tọa độ vượt kích thước ma trận");
    }
    if (!Number.isFinite(e.value)) {
      throw new RangeError("Chỉ chấp nhận giá trị số hữu hạn");
    }
    if (e.value !== 0) {
      sorted.push({ row: e.row, col: e.col, value: e.value });
    }
  }

  sorted.sort((a, b) => a.row - b.row || a.col - b.col);

  const entries: Entry[] = [];
  for (const e of sorted) {
    const last = entries[entries.length - 1];
    if (last && last.row === e.row && last.col === e.col) {
      const sum = last.value + e.value;
      if (!Number.isFinite(sum)) {
        throw new RangeError("Tổng các mục trùng vượt phạm vi số");
      }
      if (sum === 0) {
        entries.pop();
      } else {
        entries[entries.length - 1] = { ...last, value: sum };
      }
    } else {
      entries.push(e);
    }
  }

  return { rows, cols, entries };
}

function toCSR(coo: COO): CSR {
  // COO đã được sắp theo (row, col).
  const rowPtr = new Array<number>(coo.rows + 1).fill(0);
  for (const e of coo.entries) rowPtr[e.row + 1]++;

  for (let r = 1; r <= coo.rows; r++) {
    rowPtr[r] += rowPtr[r - 1];
  }

  return {
    rows: coo.rows,
    cols: coo.cols,
    rowPtr,
    colIdx: coo.entries.map(e => e.col),
    values: coo.entries.map(e => e.value)
  };
}

function toCSC(coo: COO): CSC {
  // Đếm số mục từng cột, rồi tính prefix sum.
  const colPtr = new Array<number>(coo.cols + 1).fill(0);
  for (const e of coo.entries) colPtr[e.col + 1]++;

  for (let c = 1; c <= coo.cols; c++) {
    colPtr[c] += colPtr[c - 1];
  }

  const cursor = colPtr.slice(0, coo.cols);
  const rowIdx = new Array<number>(coo.entries.length);
  const values = new Array<number>(coo.entries.length);

  // Duyệt COO theo hàng tăng nên rowIdx trong mỗi cột tăng.
  for (const e of coo.entries) {
    const k = cursor[e.col]++;
    rowIdx[k] = e.row;
    values[k] = e.value;
  }

  return { rows: coo.rows, cols: coo.cols, colPtr, rowIdx, values };
}

function getCSR(a: CSR, r: number, c: number): number {
  if (
    !Number.isSafeInteger(r) || r < 0 || r >= a.rows ||
    !Number.isSafeInteger(c) || c < 0 || c >= a.cols
  ) {
    throw new RangeError("Tọa độ ngoài ma trận");
  }

  // Binary search: colIdx tăng trong từng hàng.
  let lo = a.rowPtr[r];
  let hi = a.rowPtr[r + 1] - 1;
  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2);
    const col = a.colIdx[mid];
    if (col === c) return a.values[mid];
    if (col < c) lo = mid + 1;
    else hi = mid - 1;
  }
  return 0;
}

function multiplyCSR(a: CSR, x: readonly number[]): number[] {
  if (x.length !== a.cols) {
    throw new RangeError("Vector x phải có đúng số cột của A");
  }
  const y = new Array<number>(a.rows).fill(0);

  for (let r = 0; r < a.rows; r++) {
    for (let k = a.rowPtr[r]; k < a.rowPtr[r + 1]; k++) {
      y[r] += a.values[k] * x[a.colIdx[k]];
    }
  }
  return y;
}

function transposeCSRViewOfCSC(a: CSC): CSR {
  // Cách nhìn CSR(A^T) trên chính các mảng của CSC(A).
  // Chỉ dùng chung an toàn khi coi các mảng là bất biến.
  return {
    rows: a.cols,
    cols: a.rows,
    rowPtr: a.colPtr,
    colIdx: a.rowIdx,
    values: a.values
  };
}

const coo = makeCOO(4, 5, [
  { row: 3, col: 4, value: 9 },
  { row: 1, col: 4, value: -1 },
  { row: 0, col: 3, value: 7 },
  { row: 3, col: 1, value: 4 },
  { row: 2, col: 2, value: 0 },   // bỏ zero tường minh
  { row: 1, col: 0, value: 5 },
  { row: 1, col: 4, value: -1 }  // gộp thành -2
]);

const csr = toCSR(coo);
const csc = toCSC(coo);

console.log(coo.entries.length); // 5
console.log(csr.rowPtr);         // [0, 1, 3, 3, 5]
console.log(csr.colIdx);         // [3, 0, 4, 1, 4]
console.log(csr.values);         // [7, 5, -2, 4, 9]

console.log(csc.colPtr);         // [0, 1, 2, 2, 3, 5]
console.log(csc.rowIdx);         // [1, 3, 0, 1, 3]
console.log(csc.values);         // [5, 4, 7, -2, 9]

console.log(getCSR(csr, 1, 4));  // -2
console.log(getCSR(csr, 2, 2));  // 0: tọa độ không lưu
console.log(multiplyCSR(csr, [1, 2, 3, 4, 5]));
// [28, -5, 0, 53]

const at = transposeCSRViewOfCSC(csc);
console.log(at.rows, at.cols);   // 5, 4
console.log(at.rowPtr);          // [0, 1, 2, 2, 3, 5]
```

### 7.1. Vì sao `makeCOO` gộp và sắp trước?

Hàng/cột của một ma trận thưa là **tọa độ**, không phải danh sách độc lập. Nếu đầu vào chứa hai mục `(1,4,-1)`, chương trình cộng thành đúng một ô `(1,4,-2)`. COO canonical không còn trùng tọa độ, có thể chuyển sang CSR/CSC mà không làm tăng giả tạo `nnz`.

Nếu hai mục tại cùng tọa độ có tổng `0`, kết quả không còn mục lưu ở đó. Đối với số thực dấu phẩy động, phép cộng có sai số và phụ thuộc thứ tự; quy tắc dùng ngưỡng `epsilon` để xem gần `0` là `0` phải được lựa chọn theo nhu cầu bài toán, không mặc định coi mọi số nhỏ là zero.

### 7.2. Vì sao `toCSC` không cần sắp lại toàn bộ?

Sau khi `makeCOO` sắp theo `row` rồi `col`, thuật toán `toCSC` duyệt các mục theo **hàng tăng**. Mỗi mục được đưa vào ô trống tiếp theo của cột tương ứng bằng mảng `cursor`. Như vậy, trong từng cột, thứ tự hàng của các mục đã được chèn luôn tăng. Đây là phép **phân phối ổn định theo cột**.

Mảng `colPtr` là mốc bắt đầu và **không bị sửa khi phân phối**; `cursor` là bản sao chỉ dùng để tăng vị trí ghi. Nếu dùng chính `colPtr` để tăng con trỏ, bạn sẽ làm mất thông tin bắt đầu cột.

### 7.3. Lần theo phép nhân ma trận–vector

Với `x = [1,2,3,4,5]ᵀ`:

\[
y=Ax=
\begin{bmatrix}
7\cdot4\\
5\cdot1+(-2)\cdot5\\
0\\
4\cdot2+9\cdot5
\end{bmatrix}
=
\begin{bmatrix}
28\\
-5\\
0\\
53
\end{bmatrix}.
\]

Trong `multiplyCSR`, mỗi phần tử khác 0 chỉ được đọc một lần. Hàng rỗng `2` có `rowPtr[2] === rowPtr[3]` nên vòng lặp không chạy và `y[2]` giữ nguyên `0`. Thời gian tính trên ma trận CSR là `O(m + nnz)` để khởi tạo `y` và duyệt các mục, chưa tính việc cấp phát/chuẩn bị `x`.

## 8. Ma trận thưa và các phép toán thường gặp

| Thao tác | COO chưa có chỉ mục | CSR canonical | CSC canonical |
|---|---|---|---|
| Thêm mục trong giai đoạn xây dữ liệu | `O(1)` khấu hao để append; cần gộp về sau | Có thể cần dời nhiều mục và cập nhật `rowPtr` | Có thể cần dời nhiều mục và cập nhật `colPtr` |
| Đọc tất cả mục của một hàng `r` | Thường quét `O(nnz)` | `O(1+nnz_r)` | Thường phải dò nhiều cột hoặc xây chỉ mục hỗ trợ |
| Đọc tất cả mục của một cột `c` | Thường quét `O(nnz)` | Thường phải dò nhiều hàng hoặc xây chỉ mục hỗ trợ | `O(1+nnz_c)` |
| Tra cứu `A[r,c]` | `O(nnz)` nếu không sắp | `O(log(1+nnz_r))` nếu cột trong hàng đã sắp | `O(log(1+nnz_c))` nếu hàng trong cột đã sắp |
| Nhân `y = Ax` | `O(m+nnz)` khi cộng trực tiếp từng bộ ba | `O(m+nnz)`, thuận tiện theo hàng | `O(m+n+nnz)` nếu quét từng cột và cộng vào `y` |
| Chuyển vị `Aᵀ` | Đổi `row`/`col` của mỗi mục, `O(nnz)` trước khi sắp canonical | Diễn giải như CSC(`Aᵀ`) khi chia sẻ dữ liệu bất biến | Diễn giải như CSR(`Aᵀ`) khi chia sẻ dữ liệu bất biến |

`nnz_r` và `nnz_c` lần lượt là số phần tử được lưu ở hàng `r` và cột `c`. Thời gian ghi trong bảng phụ thuộc việc định dạng đã canonical và có cần **thay đổi cấu trúc** (thêm hoặc loại tọa độ) hay chỉ thay **giá trị của một mục đã có**.

Nếu khóa tọa độ đã tồn tại, thay `values[k]` trong CSR/CSC có thể chỉ mất `O(1)` sau khi đã tìm được vị trí `k`. Nhưng nếu thay `0` thành khác `0` hoặc ngược lại, số mục thay đổi nên có thể phải dời `O(nnz)` ô và cập nhật `O(m)` hoặc `O(n)` con trỏ. Đây là lý do thường **xây dựng ở COO**, chuẩn hóa rồi **đổi sang CSR/CSC khi tính toán**.

### 8.1. Từ CSR sang CSC trực tiếp

Không bắt buộc dựng COO trung gian. Thuật toán phổ biến:

1. Đếm `colIdx` để biết mỗi cột có bao nhiêu mục.
2. Cộng dồn thành `colPtr`.
3. Tạo `cursor = colPtr.copy()`.
4. Duyệt lần lượt từng hàng của CSR, phân phối `(row, value)` vào vị trí tiếp theo của cột tương ứng trong CSC.

Với `m` hàng, `n` cột, `nnz` mục, thuật toán tốn `O(m+n+nnz)` thời gian và `O(n+nnz)` không gian để chứa CSC (ngoài dữ liệu đầu vào); các mục trong cùng cột được sắp theo hàng nếu duyệt hàng tăng. Chiều ngược CSC → CSR dùng thuật toán đối xứng.

### 8.2. Những thao tác cần lưu ý

- **Cộng hai ma trận thưa:** có thể trộn các tọa độ đã sắp; một số giá trị cộng thành `0` nên `nnz` của kết quả không nhất thiết là tổng `nnz` của hai ma trận.
- **Nhân hai ma trận thưa:** phức tạp hơn nhân vector, vì có thể sinh nhiều tích trung gian và tọa độ trùng. Chi phí còn phụ thuộc mô hình thưa và chiến lược gom tích; không thể chỉ lấy `O(nnz_A + nnz_B)` làm độ phức tạp tổng quát.
- **Ma trận rất mất cân đối:** CSR có `m + 1` con trỏ, CSC có `n + 1` con trỏ. Nếu `m` rất lớn còn `n` nhỏ (hoặc ngược lại), chỉ riêng mảng con trỏ cũng có thể đáng kể.
- **Cập nhật nhiều lần:** khi phải chèn/xóa thường xuyên, COO, cấu trúc ánh xạ theo tọa độ hoặc dạng danh sách/dictionary trung gian có thể thích hợp hơn; chỉ nén sau khi cấu trúc ổn định.

## 9. So sánh chi phí bộ nhớ

Giả sử mỗi giá trị dùng `v` byte và mỗi chỉ số/con trỏ dùng `i` byte. Bỏ qua phần phụ trội của đối tượng và mảng trong runtime:

\[
\begin{aligned}
M_{\mathrm{dense}} &= mn\cdot v,\\
M_{\mathrm{COO}} &\approx nnz\cdot(v+2i),\\
M_{\mathrm{CSR}} &\approx nnz\cdot(v+i)+(m+1)\cdot i,\\
M_{\mathrm{CSC}} &\approx nnz\cdot(v+i)+(n+1)\cdot i.
\end{aligned}
\]

Trong đó `i` phải đủ lớn để lưu cả **chỉ số tọa độ lẫn offset `0..nnz`**. Với `Float64` (8 byte) và chỉ số 32 bit (4 byte) khi dữ liệu nằm trong giới hạn biểu diễn:

| Cách lưu | Dung lượng xấp xỉ |
|---|---|
| Dense | `8mn` byte |
| COO | `16nnz` byte |
| CSR | `12nnz + 4(m+1)` byte |
| CSC | `12nnz + 4(n+1)` byte |

Xét ma trận lớn kích thước `10.000 × 10.000` chỉ có `100.000` mục khác 0 (mật độ `0,1%`):

```text
Dense: 10.000 × 10.000 × 8
     = 800.000.000 byte  ≈ 800 MB

COO: 100.000 × 16
   =   1.600.000 byte  ≈ 1,60 MB

CSR: 100.000 × 12 + (10.000+1) × 4
   =   1.240.004 byte  ≈ 1,24 MB

CSC: tương tự CSR vì số hàng = số cột
   =   1.240.004 byte  ≈ 1,24 MB
```

Đây là **ước lượng cho các mảng dữ liệu dạng khối phẳng**, không phải số byte chính xác của các `number[]` JavaScript trong ví dụ. Các mảng JavaScript có header, ô tham chiếu, cơ chế quản lý và khả năng cấp phát dư. Với `TypedArray`, chi phí dữ liệu thường sát công thức hơn.

**Không phải ma trận nào cũng nên nén.** Nếu `nnz` gần `mn`, việc lưu chỉ số có thể khiến COO/CSR/CSC tốn **nhiều hơn** dense. Với ma trận rất thấp, số con trỏ `m+1` có thể lớn so với `nnz`, đặc biệt khi có rất nhiều hàng rỗng. Việc chọn định dạng phải dựa trên cả **mật độ**, **hình dạng**, **khả năng nén** và **thao tác truy cập**, không chỉ vào khẩu hiệu “ma trận thưa thì luôn tiết kiệm”.

## 10. Ứng dụng: từ ma trận sang đồ thị và học máy

### 10.1. Danh sách kề của đồ thị

Cho đồ thị có `m` đỉnh nguồn và `n` đỉnh đích, đặt `A[u,v] = w` nếu có cạnh từ `u` đến `v`. CSR sẽ nhóm các cạnh xuất phát từ cùng đỉnh `u`:

```text
rowPtr[u] .. rowPtr[u+1] = đoạn cạnh đi ra từ u
colIdx[k]                = đỉnh đích của cạnh k
values[k]                = trọng số cạnh k
```

Nếu không cần trọng số, `values` có thể được bỏ trong một cấu trúc danh sách kề nén chuyên biệt. CSC tương ứng thuận lợi để liệt kê các cạnh **đi vào** một đỉnh.

Lưu ý: một đồ thị có nhiều cạnh song song giữa cùng cặp đỉnh có thể yêu cầu **giữ nhiều mục trùng tọa độ**. Nếu gộp trùng bằng phép cộng như `makeCOO`, ta sẽ mất thông tin từng cạnh. Vì vậy, cần chọn rõ ý nghĩa của dữ liệu trước khi áp dụng chuẩn hóa ma trận.

### 10.2. Học máy và dữ liệu đặc trưng

Trong một ma trận dữ liệu `X`, hàng thường đại diện cho mẫu và cột là đặc trưng:

- **CSR:** truy cập toàn bộ đặc trưng khác 0 của một mẫu nhanh; phù hợp xử lý từng mẫu và nhân `Xw`.
- **CSC:** lấy tất cả mẫu có giá trị khác 0 ở một đặc trưng nhanh; thuận lợi cho một số thuật toán duyệt/cập nhật theo cột.
- **COO:** dễ lắp ghép dữ liệu từ các sự kiện `(sample, feature, value)` trước khi chuẩn hóa.

Nếu giá trị `0` và “chưa đo/không có dữ liệu” mang nghĩa khác nhau, nên dùng mask hoặc cấu trúc bổ sung cho giá trị thiếu. Ma trận thưa toán học không tự giải quyết bài toán dữ liệu thiếu.

### 10.3. Phương trình tuyến tính và tính toán khoa học

Các hệ tuyến tính `Ax=b` sinh từ lưới, đồ thị hay phương pháp phần tử hữu hạn thường có rất ít hệ số khác 0 trong mỗi hàng/cột. CSR thuận tiện cho các vòng lặp nhân `Ax` trong nhiều thuật toán lặp. CSC thuận tiện trong một số quá trình phân tích nhân tử thưa và thuật toán làm việc theo cột.

Thư viện số trị có thể yêu cầu **thứ tự chỉ số, không trùng tọa độ, chỉ số 32/64 bit**, hoặc quy ước lưu phần tam giác. Cần kiểm tra hợp đồng của từng thư viện trước khi truyền dữ liệu.

## 11. Các lỗi thường gặp và cách tự kiểm tra

### Lỗi 1 — Sai độ dài mảng con trỏ

CSR phải có `m+1` phần tử trong `rowPtr` và CSC phải có `n+1` phần tử trong `colPtr`, kể cả khi `nnz=0`. Ví dụ, một ma trận `3×2` toàn zero có:

```text
COO:  rows=[], cols=[], values=[]
CSR:  rowPtr=[0,0,0,0], colIdx=[], values=[]
CSC:  colPtr=[0,0,0],   rowIdx=[], values=[]
```

### Lỗi 2 — Hiểu nhầm khoảng đóng

Đoạn hàng là `[rowPtr[r],rowPtr[r+1])`, **không gồm** đầu mút bên phải. Nếu duyệt tới cả `rowPtr[r+1]`, sẽ đọc lấn sang hàng sau hoặc vượt cuối mảng.

### Lỗi 3 — Bỏ hàng hoặc cột rỗng khi tạo prefix sum

Với ma trận ví dụ, `rowPtr[2]=rowPtr[3]=3` và `colPtr[2]=colPtr[3]=2`. Việc lặp lại offset là hợp lệ. Nếu bỏ qua mục rỗng, chiều dài mảng con trỏ và ý nghĩa hàng/cột bị sai.

### Lỗi 4 — Chỉ đổi tên mảng CSR thành CSC

CSR(A) và CSC(A) có thể khác thứ tự `values`. Phải phân phối lại đúng tọa độ. Chỉ có quan hệ “CSC(A) như CSR(Aᵀ)” mới cho phép diễn giải lại mảng nén mà không đổi thứ tự dữ liệu.

### Lỗi 5 — Giả định tọa độ không bao giờ trùng

Nếu nhập trùng `(row,col)` mà thuật toán phía sau giả định unique, `get` hoặc phép nhân có thể cho kết quả bất ngờ. Quy tắc gộp phải được công bố và kiểm tra.

### Lỗi 6 — Coi kiểu `readonly` là bất biến runtime

TypeScript `readonly number[]` chặn sửa qua tham chiếu được khai báo như vậy nhưng không đóng băng mảng lúc chạy. Trong hệ thống có chia sẻ buffer, phải có quyền sở hữu rõ ràng để không ai làm hỏng snapshot.

### Lỗi 7 — Bỏ qua chi phí thay đổi cấu trúc

CSR/CSC rất tiện khi mẫu vị trí khác 0 đã ổn định. Chèn một tọa độ mới có thể cần dời mảng `O(nnz)` và cập nhật nhiều offset. Nếu hệ thống cập nhật thường xuyên, nên dùng dạng xây dựng linh hoạt và nén theo từng đợt.

### Lỗi 8 — Dùng chỉ số không đủ rộng

`rowPtr[m]` hoặc `colPtr[n]` bằng `nnz`, nên kiểu chỉ số phải chứa được `nnz`, không chỉ chứa được `m` hoặc `n`. Ma trận rất lớn có thể cần offset 64 bit và phải lưu ý giới hạn `number` an toàn trong JavaScript.

## 12. Bài tập vận dụng có hướng giải

**Bài 1 — lập COO.** Với ma trận `3 × 4`:

\[
B =
\begin{bmatrix}
0&2&0&0\\
0&0&0&0\\
-3&0&0&5
\end{bmatrix}
\]

Hãy viết COO canonical theo `row` rồi `col`.

**Đáp án:** `rows=[0,2,2]`, `cols=[1,0,3]`, `values=[2,-3,5]`.

**Bài 2 — chuyển sang CSR.** Với `B` ở bài 1, hãy tính `rowPtr` và `colIdx`.

**Đáp án:** Các hàng có số mục `[1,0,2]`, nên `rowPtr=[0,1,1,3]`, `colIdx=[1,0,3]`. Hàng thứ hai rỗng nên có hai offset bằng nhau.

**Bài 3 — chuyển sang CSC.** Với `B`, hãy tính `colPtr`, `rowIdx` và `values` theo thứ tự cột.

**Đáp án:** Các cột có số mục `[1,1,0,1]`; `colPtr=[0,1,2,2,3]`, `rowIdx=[2,0,2]`, `values=[-3,2,5]`.

**Bài 4 — nhân vector.** Với `A` ở đầu bài và `x=[1,2,3,4,5]ᵀ`, tính `Ax` từ CSR mà không dựng lại ma trận dense.

**Đáp án:** `Ax=[28,-5,0,53]ᵀ`. Hàng `2` có đoạn rỗng nên kết quả ở vị trí đó là `0`.

**Bài 5 — xử lý trùng.** Dữ liệu nhập COO gồm `(0,1,5), (0,1,-5), (1,0,8)` với quy tắc cộng tọa độ trùng rồi loại zero. `nnz` sau chuẩn hóa bằng bao nhiêu?

**Đáp án:** `nnz=1`, chỉ còn `(1,0,8)`. Hai mục tại `(0,1)` triệt tiêu nhau.

**Bài 6 — chọn định dạng.** Một bài toán xử lý các mẫu dữ liệu, mỗi lần cần duyệt mọi đặc trưng khác 0 của một mẫu; một bài toán khác cần duyệt tất cả mẫu có giá trị ở một đặc trưng. Dạng nào thuận lợi?

**Đáp án:** Theo mẫu/hàng thường chọn **CSR**; theo đặc trưng/cột thường chọn **CSC**. **COO** thuận lợi khi dữ liệu còn đang được thu thập và cần thêm nhiều mục mới.

**Bài 7 — bộ nhớ.** Cho `m=n=10.000`, `nnz=100.000`, giá trị `Float64` và chỉ số 4 byte. Tính dung lượng CSR chỉ gồm mảng dữ liệu, bỏ qua overhead.

**Đáp án:** `12×100.000+4×(10.000+1)=1.240.004` byte, khoảng `1,24 MB` hệ thập phân.

## 13. Tổng kết: chọn dạng lưu theo phép toán

COO biểu diễn ma trận bằng các **bộ ba tọa độ**, phù hợp nhất khi cần tạo ma trận từ nhiều mục rời rạc hoặc chuyển đổi dữ liệu. CSR dùng **`rowPtr`** để biến từng hàng thành một đoạn liên tiếp của `values/colIdx`, phù hợp truy cập theo hàng và nhân ma trận–vector. CSC dùng **`colPtr`** để biến từng cột thành một đoạn của `values/rowIdx`, phù hợp truy cập theo cột.

Ba định dạng cùng giữ nguyên ý nghĩa của một ma trận khi được xây đúng, nhưng **khác nhau về thứ tự lưu, chi phí truy cập và chi phí cập nhật**. Để dùng chúng an toàn, hãy luôn kiểm tra kích thước mảng con trỏ, mốc đầu/cuối, các khoảng nửa mở, hàng/cột rỗng, tọa độ trùng và quy tắc xử lý giá trị zero. Những bất biến đó chính là cầu nối từ kiến thức về mảng, prefix sum và độ phức tạp tới một cấu trúc lưu trữ gọn có ích trong hệ thống thực.
