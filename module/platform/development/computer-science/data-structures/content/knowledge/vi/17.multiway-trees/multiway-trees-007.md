# Xóa bằng mượn khóa, gộp nút và điều chỉnh gốc

Thêm khóa vào **B-tree** có thể làm một nút đầy và phải **tách nút**. Ngược lại, **xóa khóa** có thể khiến một nút còn quá ít khóa để đáp ứng quy tắc cân bằng. Khi đó, không thể chỉ bỏ khóa khỏi mảng của nút rồi kết thúc: thuật toán cần **mượn khóa từ anh em**, **gộp hai nút qua một khóa của cha**, hoặc **điều chỉnh gốc** để giữ cây hợp lệ.

Việc xóa còn phức tạp hơn khi khóa nằm trong **nút trong**, không phải lá. Nếu xóa trực tiếp khóa phân cách, các khoảng giá trị của những cây con có thể mất ý nghĩa. Cách giải quyết là thay khóa bằng **tiền nhiệm** (*predecessor*) hoặc **kế nhiệm** (*successor*) phù hợp, hoặc gộp các cây con trước khi tiếp tục xóa.

Bài học sử dụng B-tree với **bậc tối thiểu `t \ge 2`** và các khóa phân biệt. Ta sẽ phân tích từng trường hợp, truy vết thao tác trên cây `t=2`, xây dựng mã giả xóa **từ trên xuống** (*top-down deletion*), và cài đặt Java có thể chèn, tìm, xóa để quan sát kết quả.

## 1. Những bất biến phải giữ sau khi xóa

Với **bậc tối thiểu `t`**, một nút B-tree có tối đa `2t-1` khóa. Ngoại trừ gốc, mỗi nút phải có **ít nhất `t-1` khóa**.

| Loại nút | Số khóa tối thiểu | Số khóa tối đa | Số con thực |
| --- | ---: | ---: | --- |
| Lá không phải gốc | `t-1` | `2t-1` | 0 |
| Nút trong không phải gốc | `t-1` | `2t-1` | `k+1` với `k` khóa |
| Gốc là nút trong | 1 | `2t-1` | Từ 2 đến `2t` |
| Gốc là lá, cây không rỗng | 1 | `2t-1` | 0 |
| Cây rỗng | Không có khóa | Không áp dụng | Có thể dùng `root = null` |

Ngoài giới hạn số khóa và số con, cây phải bảo đảm:

1. Các khóa trong từng nút **tăng nghiêm ngặt**.
2. Nút trong có `k` khóa sẽ có đúng **`k+1` con**, mỗi con chứa khóa trong đúng khoảng được các khóa phân cách và tổ tiên quy định.
3. **Mọi lá nằm ở cùng độ sâu**, dù mỗi lá có thể có số khóa khác nhau.
4. Một lần xóa thành công làm tổng số khóa của cây **giảm đúng một**, không làm mất các khóa khác.

Với `t=2`, nút không phải gốc phải có 1–3 khóa; với `t=3`, phải có 2–5 khóa. Vì thế, điều kiện **thiếu khóa** (*underflow*) phụ thuộc vào `t`, không chỉ vào việc nút đã hoàn toàn rỗng hay chưa.

### Trạng thái trước và sau phép xóa

```text
B-tree t = 2:

                       [40]
                      /    \
                    [10]  [50 | 60]

Xóa 10 bằng cách chỉ gỡ khóa khỏi lá trái:

                       [40]
                      /    \
                     [ ]  [50 | 60]
                       ^
                 lá không phải gốc có 0 khóa

Trạng thái này chưa hợp lệ để kết thúc thao tác.
```

Lá trái vừa thiếu khóa. Ta có thể **mượn khóa từ lá phải**, vì lá phải có hai khóa — nhiều hơn mức tối thiểu một khóa. Kết quả hợp lệ sẽ là:

```text
                       [50]
                      /    \
                    [40]   [60]
```

Khóa `40` từ cha đi xuống trái, khóa `50` từ anh em phải lên cha. **Không khóa nào khác bị xóa**.

## 2. Ba thao tác cấu trúc: mượn, gộp và hạ gốc

Để xóa đúng, cần phân biệt những trường hợp sửa nút khác nhau.

| Tình huống | Thao tác | Ảnh hưởng |
| --- | --- | --- |
| Anh em sát bên có **ít nhất `t` khóa** | **Mượn/luân chuyển** (*borrow/rotation*) qua khóa cha | Con cần sửa được thêm một khóa, anh em bớt một; số khóa ở cha không đổi |
| Con và anh em sát bên đều có **`t-1` khóa** | **Gộp** (*merge*) hai con cùng một khóa phân cách của cha | Tạo nút có `2t-1` khóa; cha mất một khóa và một con |
| Gốc đã mất khóa cuối, còn đúng một con | **Hạ chiều cao** (*root contraction*) bằng cách nâng con lên gốc | Chiều cao cây giảm một, không mất khóa dữ liệu |
| Gốc là lá, xóa hết khóa | Đặt cây về trạng thái rỗng | Có thể dùng `root = null` |

**Khóa phân cách ở cha cũng là dữ liệu của B-tree** theo mô hình bài học. Trong phép mượn hoặc gộp, không được tự ý loại bỏ khóa cha: nó phải được chuyển tới vị trí thích hợp.

Điểm khác biệt giữa mượn và gộp là **số khóa ở cha**: mượn giữ nguyên số khóa của cha, còn gộp làm cha giảm một khóa. Nếu cha sau gộp thiếu khóa, cần tiếp tục phục hồi bất biến ở tầng cao hơn hoặc xử lý ngoại lệ gốc.

## 3. Xóa khóa nằm ở lá

Nếu khóa nằm trong lá và việc xóa **không gây thiếu khóa**, ta chỉ cần loại phần tử đó khỏi dãy khóa của lá.

Ví dụ `t=2`:

```text
Trước:          [10 | 20 | 30]
Xóa 20:         [10 | 30]

Số khóa giảm từ 3 xuống 2, vẫn nằm trong [1, 3].
```

Với mảng khóa, cần dịch các khóa phía sau vị trí xóa sang trái:

```text
removeFromLeaf(node, index):
    # node.keys[index] là khóa cần xóa
    for j = index + 1 .. node.keyCount - 1:
        node.keys[j - 1] = node.keys[j]
    node.keyCount = node.keyCount - 1
```

Chi phí dồn khóa trong một nút là O(t) với giới hạn tối đa `2t-1` khóa.

### Khi lá đang ở mức tối thiểu

Một lá **không phải gốc** chỉ có `t-1` khóa sẽ thiếu khóa nếu xóa trực tiếp một khóa. Thuật toán xóa từ trên xuống giải quyết bằng cách: **trước khi đi sâu vào một con, bảo đảm con đó có ít nhất `t` khóa**. Nhờ vậy, khi đến lá để xóa, lá có thể mất một khóa mà vẫn còn ít nhất `t-1`.

Đây là một **bất biến tạm thời của thuật toán**, mạnh hơn cận tối thiểu của B-tree:

> Khi một lời gọi đệ quy đi vào con để tiếp tục xóa, con đó đã được chuẩn bị để có ít nhất `t` khóa, trừ những trường hợp thay đổi cấu trúc gốc được xử lý riêng.

Quy tắc này giúp tránh phải phát hiện nút thiếu khóa sau khi xóa rồi quay ngược lên để sửa.

## 4. Mượn từ anh em phải: khóa cha đi xuống, khóa anh em đi lên

Xét `t=2`:

```text
Trước khi đi xuống xóa 10:

                       [40]
                      /    \
                    [10]  [50 | 60]
                      ^       ^
                    1 khóa   2 khóa
                  cần chuẩn bị
```

Con trái có `t-1=1` khóa, anh em phải có `2 \ge t` khóa. Ta thực hiện **mượn từ phải** (*borrow from next sibling*):

1. Đưa **khóa phân cách `40` của cha** xuống **cuối** con trái.
2. Đưa **khóa nhỏ nhất `50` của anh em phải** lên thay vị trí `40` ở cha.
3. Nếu đây là các **nút trong**, chuyển **con trái nhất của anh em phải** sang làm **con phải nhất của nút đang mượn**.

```text
Sau khi mượn nhưng trước khi xóa:

                       [50]
                      /    \
                  [10 | 40] [60]

Sau khi xóa 10:

                       [50]
                      /    \
                    [40]   [60]
```

Khoảng tìm kiếm vẫn đúng: mọi khóa ở nhánh trái đều nhỏ hơn `50`, mọi khóa ở nhánh phải đều lớn hơn `50`.

### Vì sao phải chuyển một con trỏ nếu mượn ở nút trong?

Giả sử con trái và anh em phải đều là nút trong. Khi đưa khóa cha xuống con trái, nút trái có thêm một **khoảng khóa phía phải** và cần thêm một cây con tương ứng. Cây con trái nhất của anh em phải chứa các khóa thuộc khoảng mới đó, nên phải chuyển cùng với phép luân chuyển khóa.

Không chuyển con trỏ là một lỗi nghiêm trọng: nút trong có thể còn đúng số khóa nhưng thiếu con, hoặc khóa của cây con rơi sai khoảng.

## 5. Mượn từ anh em trái: thao tác đối xứng

Vẫn với `t=2`, xét:

```text
Trước khi đi xuống xóa 50:

                       [40]
                      /    \
                  [10 | 20] [50]

Con phải chỉ có 1 khóa; anh em trái có 2 khóa.
```

Ta **mượn từ trái** (*borrow from previous sibling*):

1. Đưa **khóa `40` của cha** xuống **đầu** con phải.
2. Đưa **khóa lớn nhất `20` của anh em trái** lên thay `40` ở cha.
3. Nếu các nút có con, chuyển **con phải nhất của anh em trái** thành **con trái nhất của nút đang mượn**.

```text
Sau khi mượn:

                       [20]
                      /    \
                    [10]  [40 | 50]

Sau khi xóa 50:

                       [20]
                      /    \
                    [10]  [40]
```

Trong cả hai hướng mượn, tổng số khóa của cây **chưa đổi** trước khi xóa; chỉ vị trí của các khóa phân cách thay đổi. Nút cho mượn có ít nhất `t` khóa nên sau khi nhường một khóa vẫn còn ít nhất `t-1`, không bị thiếu khóa.

### Bảng ghi nhớ chiều luân chuyển

| Hướng mượn | Khóa cha chuyển xuống | Khóa anh em chuyển lên cha | Cây con chuyển nếu là nút trong |
| --- | --- | --- | --- |
| **Từ trái** | Vào **đầu** nút nhận | Khóa **lớn nhất** của anh em trái | Con **phải nhất** của anh em trái → con **trái nhất** nút nhận |
| **Từ phải** | Vào **cuối** nút nhận | Khóa **nhỏ nhất** của anh em phải | Con **trái nhất** của anh em phải → con **phải nhất** nút nhận |

## 6. Gộp hai con khi không thể mượn

Nếu con cần đi xuống chỉ có `t-1` khóa và các anh em sát bên cũng chỉ có `t-1` khóa, không thể mượn mà vẫn giữ giới hạn tối thiểu của nút cho mượn. Khi đó ta **gộp hai con kề nhau cùng khóa phân cách ở cha**.

Ví dụ `t=2`:

```text
Trước:

                        [40]
                       /    \
                     [10]  [50]
```

Hai con đều có một khóa. Gộp cùng khóa `40` của cha:

```text
Nút mới:       [10 | 40 | 50]

Cha cũ:       [ ]                 <- tạm 0 khóa
                |
                +--> [10 | 40 | 50]
```

Vì cha đang là gốc và không còn khóa, ta **nâng con đã gộp lên làm gốc mới**. Nếu mục tiêu là xóa `10`:

```text
Sau gộp và điều chỉnh gốc:
                  [10 | 40 | 50]

Sau xóa 10:
                  [40 | 50]
```

Điểm cần nhớ về số khóa:

\[
(t-1)+1+(t-1)=2t-1.
\]

Hai nút đang ở mức tối thiểu, cộng một khóa phân cách từ cha, tạo ra một nút **đầy nhưng hợp lệ**. Nút này có đủ khóa để thuật toán tiếp tục xóa một khóa mà không trở thành thiếu khóa.

### Khi gộp các nút trong

Nếu nút trái có `t-1` khóa thì nó có `t` con; nút phải cũng có `t` con. Sau khi gộp với một khóa cha, nút mới có `2t-1` khóa và **`2t` con**:

```text
Trước gộp (t = 2):

                            [40]
                           /    \
                         [20]  [60]
                         /  \  /  \
                        A    B C    D

Gộp qua khóa 40:

                      [20 | 40 | 60]
                     /    |    |     \
                    A     B    C      D
```

Các con không được đảo thứ tự. Khi có `2t` con, mỗi con phải giữ đúng khoảng giữa các khóa phân cách của nút mới.

### Gộp làm cha mất một khóa và một con

Nếu cha có `k` khóa và `k+1` con, sau khi gộp hai con qua một khóa:

- Cha còn `k-1` khóa.
- Cha còn `k` con.
- Con mới giữ toàn bộ khóa/con của hai nút cũ cùng khóa phân cách từ cha.

Cha **không phải gốc** phải tiếp tục thỏa mức `t-1` khóa khi thao tác kết thúc. Trong thuật toán từ trên xuống, ta bảo đảm cha trên đường đệ quy đã có ít nhất `t` khóa trước khi có nguy cơ mất một khóa, do đó việc gộp có thể làm cha giảm xuống `t-1` mà vẫn hợp lệ. Nếu cha là **gốc**, ngoại lệ về cận dưới cho phép xử lý bằng cách thay gốc khi nó rỗng.

## 7. Xóa khóa nằm ở nút trong: tiền nhiệm, kế nhiệm và gộp

Khóa của một nút trong là **ranh giới giữa các cây con**. Nếu xóa khóa này mà không thay thế, ta sẽ làm sai số con hoặc các khoảng tìm kiếm.

Giả sử khóa cần xóa là `x = keys[i]` trong một nút trong. Gọi:

- `L = children[i]`: cây con ngay bên trái `x`.
- `R = children[i+1]`: cây con ngay bên phải `x`.

Có ba tình huống chuẩn.

### 7.1. Con trái có ít nhất `t` khóa: dùng tiền nhiệm

**Tiền nhiệm** (*predecessor*) của `x` là khóa lớn nhất nằm trong cây con trái `L`. Vì mọi khóa của `L` nhỏ hơn `x`, tiền nhiệm phù hợp để thay `x` mà vẫn giữ thứ tự.

Ví dụ:

```text
Trước:              [40]
                   /    \
              [10 | 20] [50]

Xóa khóa 40 ở gốc:
  - Con trái có 2 khóa >= t = 2.
  - Tiền nhiệm của 40 là 20.

Đưa 20 lên thay 40 rồi xóa 20 trong con trái:

Sau:                [20]
                   /    \
                 [10]   [50]
```

Quy tắc tổng quát:

1. Lấy khóa lớn nhất ở **đường đi phải nhất** của cây con trái.
2. Thay khóa `x` trong nút trong bằng tiền nhiệm.
3. Xóa **bản gốc tiền nhiệm** trong cây con trái bằng thuật toán xóa B-tree.

Không được chỉ thay `x` bằng tiền nhiệm mà quên xóa tiền nhiệm ở vị trí cũ, vì như vậy một khóa sẽ xuất hiện hai lần trong mô hình khóa phân biệt.

### 7.2. Con phải có ít nhất `t` khóa: dùng kế nhiệm

Nếu con trái không đủ `t` khóa nhưng con phải có, ta dùng **kế nhiệm** (*successor*): khóa nhỏ nhất nằm trong cây con phải `R`.

```text
Trước:              [40]
                   /    \
                 [10] [50 | 60]

Xóa 40:
  - Con trái có 1 khóa < t = 2.
  - Con phải có 2 khóa >= t.
  - Kế nhiệm là 50.

Sau:                [50]
                   /    \
                 [10]   [60]
```

Tương tự tiền nhiệm, phải **xóa bản gốc kế nhiệm** sau khi dùng nó thay khóa ở nút trong.

### 7.3. Cả hai con đều có `t-1` khóa: gộp cùng `x`

Nếu không con nào có thể cho phép thuật toán đi xuống xóa trực tiếp, gộp hai con kề nhau **cùng khóa `x`** từ cha:

```text
Trước:              [40]
                   /    \
                 [10]   [50]

Gộp:          [10 | 40 | 50]

Xóa 40 trong nút đã gộp:
               [10 | 50]
```

Với trường hợp tổng quát, nút mới có `2t-1` khóa. Thuật toán tiếp tục tìm/xóa `x` trong **nút đã gộp**, vốn có đủ khóa để xuống tiếp.

| Vị trí khóa cần xóa | Tình trạng hai con cạnh khóa | Cách xử lý |
| --- | --- | --- |
| Nút trong | Con trái có `>= t` khóa | Thay bằng **tiền nhiệm**, xóa bản gốc trong con trái |
| Nút trong | Con trái có `t-1` khóa, con phải có `>= t` | Thay bằng **kế nhiệm**, xóa bản gốc trong con phải |
| Nút trong | Cả hai chỉ có `t-1` khóa | **Gộp** trái + khóa cha + phải, rồi tiếp tục xóa |

Nếu cả hai con đều có từ `t` khóa, có thể chọn tiền nhiệm hoặc kế nhiệm; cài đặt ở bài này ưu tiên tiền nhiệm.

## 8. Chuẩn bị con trước khi đi xuống (*top-down deletion*)

Không phải lúc nào khóa cần xóa cũng nằm ngay tại nút hiện tại. Nếu khóa chưa có trong nút trong, việc chọn con vẫn dựa vào **khoảng khóa** như tìm kiếm thông thường.

Điểm khác với tìm kiếm: **trước khi đi xuống con `child[i]`, phải bảo đảm con đó có ít nhất `t` khóa**.

Nếu con đang có đúng `t-1` khóa, ta chuẩn bị bằng:

1. **Mượn anh em trái** nếu có anh em trái chứa ít nhất `t` khóa.
2. Nếu không, **mượn anh em phải** nếu có anh em phải chứa ít nhất `t` khóa.
3. Nếu không thể mượn, **gộp** con đó với một anh em liền kề qua một khóa của cha.

Sau bước chuẩn bị, con cần đi xuống sẽ có ít nhất `t` khóa, hoặc sẽ là nút gộp có `2t-1` khóa.

### Mã giả định tuyến và cập nhật chỉ số

```text
deleteFromNode(node, x):
    i = chỉ số đầu tiên có node.keys[i] >= x

    nếu i < node.keyCount và node.keys[i] == x:
        nếu node là lá:
            xóa khóa tại i
        ngược lại:
            xóa khóa tại nút trong bằng tiền nhiệm,
            kế nhiệm hoặc gộp
        return

    nếu node là lá:
        return  # không tìm thấy

    # x phải thuộc children[i] nếu có trong cây.
    wasRightmost = (i == node.keyCount)

    nếu children[i] chỉ có t-1 khóa:
        prepareChild(node, i)  # mượn hoặc gộp

    # Gộp với anh em TRÁI có thể làm node mất khóa cuối,
    # và nhánh cũ i trở thành nhánh i-1.
    nếu wasRightmost và i > node.keyCount:
        deleteFromNode(children[i-1], x)
    ngược lại:
        deleteFromNode(children[i], x)
```

**Vì sao phải kiểm tra lại chỉ số sau gộp?** Khi con ngoài cùng bên phải không mượn được và phải gộp với anh em **bên trái**, cha giảm một khóa và một con. Nhánh cũ ở vị trí `i` không còn tồn tại; nút đã gộp nằm tại `i-1`. Dùng chỉ số cũ có thể truy cập ngoài vùng hợp lệ hoặc đi sai con.

### Tạm thời chưa hợp lệ trong quá trình cập nhật

Khi gộp hai con dưới một **gốc chỉ có một khóa**, gốc có thể tạm trở thành nút rỗng với một con. Các thao tác trong nhánh gộp vẫn có thể hoàn thành khi giữ tham chiếu tới nút trung gian đó. **Sau khi xóa kết thúc**, thay gốc bằng con duy nhất hoặc đặt cây rỗng nếu không còn khóa.

Không được xem trạng thái gốc trung gian rỗng là B-tree hợp lệ để trả cho người dùng mà chưa điều chỉnh.

## 9. Điều chỉnh gốc và chiều cao

Gốc khác các nút còn lại vì được phép có ít khóa hơn. Nhưng khi **cây không rỗng**, gốc vẫn phải chứa **ít nhất một khóa**.

### 9.1. Gốc trong mất khóa cuối sau phép gộp

```text
Trước khi xóa:
                          [40]
                         /    \
                       [10]  [50]

Gộp hai con qua khóa cha:
                          [ ]       <- gốc tạm rỗng
                           |
                     [10 | 40 | 50]

Sau khi xóa 10, nâng con đã gộp lên:
                       [40 | 50]
```

Chiều cao giảm từ **một cạnh** (gốc tới lá) xuống **không cạnh** (gốc cũng là lá). Việc giảm độ cao diễn ra **đồng thời với toàn bộ cây**, không khiến một lá kết thúc sớm hơn các lá khác.

### 9.2. Gốc là lá và xóa khóa cuối

```text
Trước:       [42]      <- gốc là lá
Xóa 42:      [ ]       <- không còn khóa
Sau:        root = null
```

Cây rỗng được biểu diễn bằng `root = null`. Không nên tạo lại một nút mới có một khóa giả chỉ để duy trì gốc.

### 9.3. Không hạ gốc quá sớm

Nếu gốc vẫn có **ít nhất một khóa**, không được bỏ nó để nâng một con lên vì các nhánh còn lại sẽ mất liên kết hoặc vi phạm khoảng khóa. Điều chỉnh gốc chỉ cần khi **sau thao tác** số khóa gốc bằng 0.

## 10. Chương trình Java: chèn, tìm và xóa B-tree

Ví dụ này triển khai B-tree lưu **khóa `int` phân biệt** với bậc tối thiểu `t \ge 2`. Phần chèn hỗ trợ tạo cây thử nghiệm; trọng tâm là `delete`, `removeFromInternal`, `borrowFromPrev`, `borrowFromNext`, `merge` và `fill`. Lớp dùng mảng khóa và mảng con với sức chứa tối đa đúng theo `t`.

Để thao tác xóa khóa không tồn tại **không làm thay đổi hình dạng cây**, mã gọi `contains` trước khi thực sự xóa. Đây là lựa chọn giao diện: thuật toán xóa chuẩn vẫn có thể tái cân bằng trên đường tìm một khóa không tồn tại nếu không kiểm tra trước.

```java
import java.util.Arrays;

public class BTreeDeletionDemo {
    static final class Node {
        final int[] keys;
        final Node[] children;
        final boolean leaf;
        int count;

        Node(int t, boolean leaf) {
            keys = new int[2 * t - 1];
            children = new Node[2 * t];
            this.leaf = leaf;
            count = 0;
        }

        String keysText() {
            return Arrays.toString(Arrays.copyOf(keys, count));
        }
    }

    static final class BTree {
        private final int t;
        private Node root;
        private int size;

        BTree(int minimumDegree) {
            if (minimumDegree < 2
                    || minimumDegree > Integer.MAX_VALUE / 2) {
                throw new IllegalArgumentException("Invalid minimum degree");
            }
            t = minimumDegree;
        }

        int size() {
            return size;
        }

        boolean contains(int key) {
            Node node = root;
            while (node != null) {
                int i = firstNotLessThan(node, key);
                if (i < node.count && node.keys[i] == key) {
                    return true;
                }
                if (node.leaf) {
                    return false;
                }
                node = node.children[i];
            }
            return false;
        }

        private int firstNotLessThan(Node node, int key) {
            int i = 0;
            while (i < node.count && node.keys[i] < key) {
                i++;
            }
            return i;
        }

        boolean insert(int key) {
            if (root == null) {
                root = new Node(t, true);
                root.keys[0] = key;
                root.count = 1;
                size++;
                return true;
            }
            if (contains(key)) {
                return false;
            }
            if (root.count == 2 * t - 1) {
                Node newRoot = new Node(t, false);
                newRoot.children[0] = root;
                splitChild(newRoot, 0);
                root = newRoot;
            }
            insertNonFull(root, key);
            size++;
            return true;
        }

        private void splitChild(Node parent, int index) {
            Node full = parent.children[index];
            Node right = new Node(t, full.leaf);
            int middle = full.keys[t - 1];

            right.count = t - 1;
            for (int j = 0; j < t - 1; j++) {
                right.keys[j] = full.keys[j + t];
            }
            if (!full.leaf) {
                for (int j = 0; j < t; j++) {
                    right.children[j] = full.children[j + t];
                    full.children[j + t] = null;
                }
            }
            full.count = t - 1;

            for (int j = parent.count; j >= index + 1; j--) {
                parent.children[j + 1] = parent.children[j];
            }
            parent.children[index + 1] = right;
            for (int j = parent.count - 1; j >= index; j--) {
                parent.keys[j + 1] = parent.keys[j];
            }
            parent.keys[index] = middle;
            parent.count++;
        }

        private void insertNonFull(Node node, int key) {
            int i = node.count - 1;
            if (node.leaf) {
                while (i >= 0 && key < node.keys[i]) {
                    node.keys[i + 1] = node.keys[i];
                    i--;
                }
                node.keys[i + 1] = key;
                node.count++;
                return;
            }
            while (i >= 0 && key < node.keys[i]) {
                i--;
            }
            i++;
            if (node.children[i].count == 2 * t - 1) {
                splitChild(node, i);
                if (key > node.keys[i]) {
                    i++;
                }
            }
            insertNonFull(node.children[i], key);
        }

        boolean delete(int key) {
            if (root == null || !contains(key)) {
                return false;
            }
            remove(root, key);

            // Gốc rỗng sau phép gộp hoặc xóa khóa cuối.
            if (root.count == 0) {
                root = root.leaf ? null : root.children[0];
            }
            size--;
            return true;
        }

        private void remove(Node node, int key) {
            int index = firstNotLessThan(node, key);

            if (index < node.count && node.keys[index] == key) {
                if (node.leaf) {
                    removeFromLeaf(node, index);
                } else {
                    removeFromInternal(node, index);
                }
                return;
            }

            if (node.leaf) {
                return; // Không xảy ra với lần delete đã contains.
            }

            boolean wasLast = (index == node.count);
            if (node.children[index].count == t - 1) {
                fill(node, index);
            }

            // Nếu gộp con ngoài cùng bên phải vào anh em trái,
            // vị trí cũ index trở thành index - 1.
            if (wasLast && index > node.count) {
                remove(node.children[index - 1], key);
            } else {
                remove(node.children[index], key);
            }
        }

        private void removeFromLeaf(Node node, int index) {
            for (int j = index + 1; j < node.count; j++) {
                node.keys[j - 1] = node.keys[j];
            }
            node.keys[--node.count] = 0;
        }

        private int predecessor(Node node, int index) {
            Node current = node.children[index];
            while (!current.leaf) {
                current = current.children[current.count];
            }
            return current.keys[current.count - 1];
        }

        private int successor(Node node, int index) {
            Node current = node.children[index + 1];
            while (!current.leaf) {
                current = current.children[0];
            }
            return current.keys[0];
        }

        private void removeFromInternal(Node node, int index) {
            int key = node.keys[index];
            Node left = node.children[index];
            Node right = node.children[index + 1];

            if (left.count >= t) {
                int pred = predecessor(node, index);
                node.keys[index] = pred;
                remove(left, pred);
            } else if (right.count >= t) {
                int succ = successor(node, index);
                node.keys[index] = succ;
                remove(right, succ);
            } else {
                merge(node, index);
                remove(node.children[index], key);
            }
        }

        // Trước khi xuống một con có t-1 khóa, chuẩn bị cho con
        // có >=t khóa bằng mượn hoặc gộp.
        private void fill(Node parent, int index) {
            if (index > 0
                    && parent.children[index - 1].count >= t) {
                borrowFromPrev(parent, index);
            } else if (index < parent.count
                    && parent.children[index + 1].count >= t) {
                borrowFromNext(parent, index);
            } else if (index < parent.count) {
                merge(parent, index);
            } else {
                merge(parent, index - 1);
            }
        }

        private void borrowFromPrev(Node parent, int index) {
            Node child = parent.children[index];
            Node sibling = parent.children[index - 1];

            // Mở vị trí khóa đầu ở nút nhận.
            for (int j = child.count - 1; j >= 0; j--) {
                child.keys[j + 1] = child.keys[j];
            }
            if (!child.leaf) {
                for (int j = child.count; j >= 0; j--) {
                    child.children[j + 1] = child.children[j];
                }
                child.children[0] = sibling.children[sibling.count];
                sibling.children[sibling.count] = null;
            }

            child.keys[0] = parent.keys[index - 1];
            parent.keys[index - 1] = sibling.keys[sibling.count - 1];
            sibling.keys[sibling.count - 1] = 0;
            sibling.count--;
            child.count++;
        }

        private void borrowFromNext(Node parent, int index) {
            Node child = parent.children[index];
            Node sibling = parent.children[index + 1];

            // Nhận khóa cha ở cuối nút đang xét.
            child.keys[child.count] = parent.keys[index];
            if (!child.leaf) {
                child.children[child.count + 1] = sibling.children[0];
                for (int j = 1; j <= sibling.count; j++) {
                    sibling.children[j - 1] = sibling.children[j];
                }
                sibling.children[sibling.count] = null;
            }

            parent.keys[index] = sibling.keys[0];
            for (int j = 1; j < sibling.count; j++) {
                sibling.keys[j - 1] = sibling.keys[j];
            }
            sibling.keys[sibling.count - 1] = 0;
            sibling.count--;
            child.count++;
        }

        // Gộp children[index] + keys[index] + children[index+1].
        private void merge(Node parent, int index) {
            Node left = parent.children[index];
            Node right = parent.children[index + 1];
            int oldLeftCount = left.count;

            left.keys[oldLeftCount] = parent.keys[index];
            for (int j = 0; j < right.count; j++) {
                left.keys[oldLeftCount + 1 + j] = right.keys[j];
            }
            if (!left.leaf) {
                for (int j = 0; j <= right.count; j++) {
                    left.children[oldLeftCount + 1 + j] =
                        right.children[j];
                    right.children[j] = null;
                }
            }
            left.count += 1 + right.count;

            // Bỏ khóa phân cách của cha.
            for (int j = index + 1; j < parent.count; j++) {
                parent.keys[j - 1] = parent.keys[j];
            }
            parent.keys[parent.count - 1] = 0;

            // Bỏ con phải đã gộp khỏi cha.
            for (int j = index + 2; j <= parent.count; j++) {
                parent.children[j - 1] = parent.children[j];
            }
            parent.children[parent.count] = null;
            parent.count--;
        }

        String sortedKeys() {
            StringBuilder result = new StringBuilder("[");
            if (root != null) {
                appendInOrder(root, result);
            }
            return result.append("]").toString();
        }

        private void appendInOrder(Node node, StringBuilder result) {
            for (int i = 0; i < node.count; i++) {
                if (!node.leaf) {
                    appendInOrder(node.children[i], result);
                }
                if (result.length() > 1) {
                    result.append(", ");
                }
                result.append(node.keys[i]);
            }
            if (!node.leaf) {
                appendInOrder(node.children[node.count], result);
            }
        }

        String rootShape() {
            if (root == null) {
                return "(empty)";
            }
            if (root.leaf) {
                return root.keysText();
            }
            // Dùng cho ví dụ nhỏ có gốc một khóa và hai lá.
            return root.keysText() + " -> "
                + root.children[0].keysText() + " | "
                + root.children[1].keysText();
        }
    }

    // Dựng một B-tree t=2 hợp lệ có gốc một khóa và hai lá.
    static BTree sample(int[] leftKeys, int separator, int[] rightKeys) {
        BTree tree = new BTree(2);
        Node left = new Node(2, true);
        Node right = new Node(2, true);
        for (int x : leftKeys) {
            left.keys[left.count++] = x;
        }
        for (int x : rightKeys) {
            right.keys[right.count++] = x;
        }
        Node root = new Node(2, false);
        root.keys[0] = separator;
        root.count = 1;
        root.children[0] = left;
        root.children[1] = right;
        tree.root = root;
        tree.size = 1 + left.count + right.count;
        return tree;
    }

    public static void main(String[] args) {
        BTree borrowRight = sample(new int[] {10}, 40,
                                   new int[] {50, 60});
        borrowRight.delete(10);
        System.out.println("Muon phai: " + borrowRight.rootShape());

        BTree borrowLeft = sample(new int[] {10, 20}, 40,
                                  new int[] {50});
        borrowLeft.delete(50);
        System.out.println("Muon trai: " + borrowLeft.rootShape());

        BTree merge = sample(new int[] {10}, 40, new int[] {50});
        merge.delete(10);
        System.out.println("Gop + ha goc: " + merge.rootShape());

        BTree predecessorCase = sample(new int[] {10, 20}, 40,
                                       new int[] {50});
        predecessorCase.delete(40);
        System.out.println("Tien nhiem: " + predecessorCase.rootShape());

        BTree successorCase = sample(new int[] {10}, 40,
                                     new int[] {50, 60});
        successorCase.delete(40);
        System.out.println("Ke nhiem: " + successorCase.rootShape());

        BTree tree = new BTree(2);
        for (int x : new int[] {
                10, 20, 30, 40, 50, 60, 70, 80, 90, 100}) {
            tree.insert(x);
        }
        tree.delete(50);
        tree.delete(10);
        boolean missing = tree.delete(999);
        System.out.println("Con lai: " + tree.sortedKeys());
        System.out.println("size=" + tree.size()
            + ", delete(999)=" + missing);
    }
}
```

Kết quả dự kiến:

```text
Muon phai: [50] -> [40] | [60]
Muon trai: [20] -> [10] | [40]
Gop + ha goc: [40, 50]
Tien nhiem: [20] -> [10] | [50]
Ke nhiem: [50] -> [10] | [60]
Con lai: [20, 30, 40, 60, 70, 80, 90, 100]
size=8, delete(999)=false
```

### Vì sao dùng các ví dụ một tầng?

Các ví dụ `sample(...)` tạo trực tiếp **một gốc và hai lá** để buộc thuật toán đi vào từng tình huống cụ thể. Khi xóa `10` khỏi cây `[40]` có hai lá `[10]` và `[50,60]`, có thể dự đoán chắc chắn thao tác sẽ **mượn từ phải**. Khi đổi kích thước hai lá, ta buộc được tình huống **mượn từ trái** hoặc **gộp**.

Phần cuối `main` dùng `insert` để tạo một cây lớn hơn rồi gọi `delete` liên tiếp. Phương thức `sortedKeys()` duyệt theo thứ tự và cho thấy các khóa còn lại; nó không bảo đảm hai trình tự cập nhật khác nhau sẽ cho cùng **hình dạng cây**, chỉ bảo đảm tập khóa và thứ tự đúng khi cây hợp lệ.

### Một số chi tiết cài đặt cần chú ý

- **`count` khác độ dài mảng `keys`.** Mảng luôn có `2t-1` ô, còn `count` chỉ số khóa đang có. Những ô sau `count` là dự trữ.
- **Chuyển con khi mượn/gộp.** Với nút trong, không thể chỉ thao tác các khóa. Phải giữ đúng `keyCount+1` con ở từng nút.
- **Dọn tham chiếu con đã chuyển.** Đặt `null` vào ô con cũ để không giữ liên kết ngoài phần đang dùng; không hủy các nút con vẫn thuộc cây.
- **Xóa khóa nội bộ bằng tiền nhiệm/kế nhiệm.** Thay khóa ở nút hiện tại rồi xóa đúng bản gốc trong cây con thích hợp.
- **Điều chỉnh gốc sau khi xóa.** Gốc có `count=0` chỉ là trạng thái tạm thời; nếu là nút trong, nâng con duy nhất, còn nếu là lá thì cây trở thành rỗng.
- **Khóa không tồn tại.** `delete` trả về `false` và không thay đổi cây vì kiểm tra `contains` trước.

Đây là ví dụ học thuật, chưa phải thư viện hoàn chỉnh cho lưu trữ ngoài hay truy cập đồng thời. Mã giả định các thao tác cấp phát thành công, không có lỗi bộ nhớ giữa quá trình tái cấu trúc, và không triển khai cơ chế khóa trang, ghi nhật ký hoặc phục hồi sau sự cố.

## 11. Tính đúng đắn của cách xóa từ trên xuống

Có thể xem phép xóa là chuỗi thao tác bảo toàn các bất biến cấu trúc.

### 11.1. Trước khi xuống con, nó đã có đủ khóa

Nếu con dự định đi xuống có `t-1` khóa, thao tác `fill` bảo đảm con nhận được thêm khóa qua mượn hoặc gộp. Nhờ đó, bước xóa ở tầng thấp hơn không làm con kết thúc với ít hơn `t-1` khóa.

Khi mượn, anh em cho mượn bắt đầu có ít nhất `t` khóa nên sau khi mất một vẫn có `t-1`. Khi gộp, hai nút mỗi nút `t-1` khóa và một khóa cha tạo nút `2t-1` khóa, nằm trong giới hạn.

### 11.2. Các khoảng khóa được bảo toàn

Mượn khóa qua cha là **luân chuyển khóa phân cách**:

- Mượn từ trái đưa khóa lớn nhất của anh em trái lên cha, khóa cha xuống đầu nút nhận.
- Mượn từ phải đưa khóa nhỏ nhất của anh em phải lên cha, khóa cha xuống cuối nút nhận.
- Nếu nút trong có con, chuyển đúng cây con ngoài cùng tương ứng.

Gộp giữ thứ tự **khóa trái → khóa cha → khóa phải**, cùng thứ tự các cây con hai phía. Do đó, tất cả khóa tiếp tục nằm trong khoảng hợp lệ theo tổ tiên.

### 11.3. Xóa khóa ở nút trong không làm mất ranh giới

Khi dùng tiền nhiệm/kế nhiệm, khóa thay thế nằm sát khóa bị xóa theo thứ tự toàn cây. Việc thay rồi xóa bản gốc không tạo bản sao tồn tại lâu dài và không đổi quan hệ thứ tự giữa các cây con. Nếu cả hai con thiếu khóa để thay trực tiếp, việc gộp đem cả hai con về một nút mới rồi mới xóa khóa bên trong.

### 11.4. Độ sâu lá không bị lệch

Mượn khóa và gộp nút không đưa một nhánh xuống tầng sâu hơn các nhánh khác. Nếu gộp làm gốc rỗng, việc hạ gốc khiến **toàn bộ cây giảm một tầng**. Vì thế mọi lá vẫn cùng độ sâu sau khi hoàn tất phép xóa.

### 11.5. Mỗi lần xóa thành công chỉ giảm một khóa

Mượn và gộp chỉ **chuyển vị trí** các khóa. Trong trường hợp xóa ở nút trong bằng tiền nhiệm/kế nhiệm, khóa thay thế vẫn tồn tại tại nút trong nhưng bản gốc bị loại khỏi cây con. Kết quả cuối cùng là **đúng một khóa bị xóa** khỏi tập khóa toàn cây.

## 12. Độ phức tạp của xóa B-tree

Gọi `n` là số khóa, `t` là bậc tối thiểu và `h` là chiều cao của cây. Với B-tree cân bằng:

\[
h=O(\log_t(n+1)).
\]

Trong chương trình Java này, mỗi tầng quét các khóa để tìm vị trí; mượn hoặc gộp có thể phải dịch/chuyển O(t) ô khóa và con trỏ.

| Công việc | Chi phí |
| --- | --- |
| Tìm vị trí trong một nút theo quét tuyến tính | O(t) |
| Mượn một khóa qua cha | O(t) trong trường hợp xấu do dịch mảng |
| Gộp hai nút | O(t) |
| Số tầng đệ quy của một lần xóa | O(log_t(n+1)) |
| Tổng thời gian khi `t` thay đổi theo quy mô | O(t log_t(n+1)) trong mô hình đơn giản |
| Tổng thời gian nếu `t` là hằng số | **O(log(n+1))** |
| Bộ nhớ phụ trợ cho đệ quy | O(log_t(n+1)) |

Việc `contains` trước `delete` làm thêm một lượt tìm kiếm, nhưng không đổi bậc thời gian trong mô hình trên. Khi không cần giữ nguyên hình dạng cây nếu khóa vắng mặt, có thể thiết kế API xóa trực tiếp và trả về trạng thái thành công/thất bại mà không phải tìm trước.

Đối với cấu trúc lưu theo trang đĩa, chi phí còn gồm việc nạp hoặc ghi lại nút cha, con và anh em. Mượn/gộp có thể đụng tới **nhiều trang ở một tầng**. Số lần truy cập trang theo đường tìm vẫn gắn với chiều cao trong mô hình mỗi nút là một trang, nhưng **không nên đồng nhất** số phép so sánh CPU, số trang logic bị thay đổi và số I/O vật lý khi hệ thống có cache hoặc cơ chế ghi trì hoãn.

## 13. Những lỗi thường gặp

1. **Chỉ xóa khóa khỏi lá tối thiểu rồi kết thúc.** Nút không phải gốc có thể còn dưới `t-1` khóa; phải mượn hoặc gộp.
2. **Mượn từ anh em cũng đang có `t-1` khóa.** Sau cho mượn, anh em sẽ thiếu khóa; chỉ mượn từ anh em có ít nhất `t`.
3. **Đưa khóa anh em trực tiếp sang nút nhận, bỏ qua khóa cha.** Khóa phân cách phải được luân chuyển qua cha để giữ đúng miền tìm kiếm.
4. **Mượn ở nút trong nhưng quên chuyển một cây con.** Nút mới sẽ có sai số con hoặc cây con nằm sai khoảng.
5. **Gộp hai nút nhưng quên lấy khóa phân cách từ cha.** Nút gộp sẽ thiếu một khóa và cha không được cập nhật đúng.
6. **Sau gộp không giảm `keyCount` và số con thực của cha.** Tìm kiếm có thể đi theo liên kết đã bị loại.
7. **Không cập nhật chỉ số khi gộp con ngoài cùng bên phải với anh em trái.** Con gộp nằm tại `i-1`, không còn ở `i` cũ.
8. **Xóa khóa ở nút trong mà không thay bằng tiền nhiệm hoặc kế nhiệm phù hợp.** Ranh giới giữa các cây con bị phá.
9. **Thay khóa bằng tiền nhiệm nhưng quên xóa bản gốc tiền nhiệm.** Khóa xuất hiện hai lần trong cây khóa phân biệt.
10. **Giữ một gốc rỗng có một con sau khi kết thúc.** Phải nâng con duy nhất hoặc trả cây rỗng nếu không còn phần tử.
11. **Điều chỉnh gốc khi nó vẫn có khóa.** Có thể làm mất liên kết tới các cây con khác và phá cấu trúc.
12. **Cho rằng mượn luôn làm giảm chiều cao.** Mượn chỉ đổi khóa giữa những nút cùng tầng; chiều cao chỉ giảm khi nâng con thay gốc rỗng.
13. **Cho rằng gộp luôn làm giảm chiều cao.** Gộp dưới một nút trong không phải gốc chỉ thay đổi số nút ở tầng đó; hạ chiều cao chỉ xảy ra khi gốc được thay.
14. **Nhầm “bậc `t`” là số khóa tối đa.** Với **minimum degree `t`**, nút có tối đa `2t-1` khóa; nếu tài liệu định nghĩa order theo cách khác, công thức sửa nút có thể khác.
15. **Không kiểm tra cây con theo cận của tổ tiên.** Các nút có thể đủ khóa và con mà vẫn sai tính chất tìm kiếm nếu con trỏ bị đặt nhầm.

## 14. Tự kiểm tra

**Câu 1.** Với B-tree `t=3`, một nút không phải gốc đang có hai khóa. Nếu xóa một khóa trực tiếp, nó có hợp lệ không?

**Đáp án:** Không. Cận dưới là `t-1=2` khóa; còn một khóa là thiếu. Cần bảo đảm nút có ít nhất `t=3` khóa trước khi đi xuống xóa theo thuật toán top-down, hoặc sửa thiếu khóa sau xóa bằng chiến lược khác.

**Câu 2.** Cây `t=2` có gốc `[40]`, lá trái `[10]` và lá phải `[50,60]`. Xóa `10` sẽ dùng thao tác nào?

**Đáp án:** Mượn từ anh em phải. Đưa `40` xuống trái, `50` lên gốc, rồi xóa `10`. Kết quả: gốc `[50]`, hai lá `[40]` và `[60]`.

**Câu 3.** Với gốc `[40]`, lá trái `[10,20]` và lá phải `[50]` trong cây `t=2`, xóa `50` sẽ mượn từ đâu?

**Đáp án:** Mượn từ trái: đưa `40` xuống phải, `20` từ trái lên gốc, rồi xóa `50`. Kết quả: gốc `[20]`, hai lá `[10]` và `[40]`.

**Câu 4.** Hai nút anh em mỗi nút có `t-1` khóa, gộp cùng một khóa cha sẽ có bao nhiêu khóa?

**Đáp án:** `(t-1)+1+(t-1)=2t-1` khóa, bằng dung lượng tối đa của một nút B-tree theo quy ước `t`.

**Câu 5.** Khi gộp hai nút trong, tổng số con của nút gộp là bao nhiêu?

**Đáp án:** `2t` con: mỗi nút trước gộp có `t` con vì có `t-1` khóa. Nút sau gộp có `2t-1` khóa và phải có `2t` con.

**Câu 6.** Vì sao không thể mượn khóa từ một anh em chỉ có `t-1` khóa?

**Đáp án:** Sau cho mượn, anh em chỉ còn `t-2` khóa, dưới mức tối thiểu `t-1` của nút không phải gốc.

**Câu 7.** Khóa `40` nằm ở gốc, con trái `[10,20]`, con phải `[50]`, `t=2`. Khi xóa `40`, chọn phương án nào?

**Đáp án:** Con trái có ít nhất `t` khóa, nên dùng tiền nhiệm `20` thay `40` rồi xóa `20` khỏi con trái. Gốc trở thành `[20]` với lá trái `[10]` và lá phải `[50]`.

**Câu 8.** Nếu con trái chỉ có `t-1` khóa nhưng con phải có ít nhất `t` khóa khi xóa khóa ở nút trong, dùng loại khóa thay thế nào?

**Đáp án:** Dùng **kế nhiệm** từ cây con phải, thay vào nút trong rồi xóa bản gốc kế nhiệm trong cây con đó.

**Câu 9.** Gốc `[40]` có hai lá `[10]` và `[50]` trong cây `t=2`. Xóa `40` sẽ làm gì?

**Đáp án:** Gộp hai lá với khóa `40` thành `[10,40,50]`, xóa `40` để còn `[10,50]`, rồi nâng nút gộp lên làm gốc mới.

**Câu 10.** Vì sao sau `fill(parent,i)` phải kiểm tra lại chỉ số khi đang đi theo con ngoài cùng bên phải?

**Đáp án:** Nếu con ngoài cùng bên phải bị gộp với anh em trái, cha giảm một khóa và con gộp nằm ở vị trí `i-1`; chỉ số `i` cũ không còn hợp lệ.

**Câu 11.** Sau một lần mượn khóa hợp lệ, số khóa ở nút cha có thay đổi không?

**Đáp án:** Không. Một khóa của cha xuống con và một khóa của anh em lên cha. Số khóa cha giữ nguyên, chỉ giá trị khóa phân cách thay đổi.

**Câu 12.** Sau một lần gộp hai con, số khóa và số con của cha thay đổi thế nào?

**Đáp án:** Cha giảm đúng **một khóa** và **một con thực**. Con gộp giữ các khóa và con từ cả hai nút cũ cùng khóa phân cách được lấy từ cha.

**Câu 13.** Có phải mỗi lần xóa B-tree đều làm chiều cao giảm một không?

**Đáp án:** Không. Hầu hết thao tác giữ nguyên chiều cao. Chỉ khi gốc mất khóa cuối và được thay bằng con duy nhất, chiều cao giảm một; xóa phần tử cuối cùng đưa cây về rỗng.

**Câu 14.** Với `t` cố định, thao tác xóa trong B-tree có độ phức tạp thời gian nào theo số khóa `n`?

**Đáp án:** O(log n). Mỗi tầng sửa tối đa một số lượng nút hằng số và xử lý O(t) ô, còn chiều cao O(log_t n) khi cây hợp lệ.

**Câu 15.** Một thuật toán xóa thay khóa trong nút trong bằng tiền nhiệm nhưng không xóa tiền nhiệm ở lá sẽ vi phạm tính chất gì?

**Đáp án:** Khóa tiền nhiệm xuất hiện ở hai vị trí, phá giả định khóa phân biệt và khiến số khóa toàn cây không giảm đúng một.

**Câu 16.** Khi xóa `42` khỏi cây chỉ gồm nút gốc lá `[42]`, trạng thái sau cùng là gì?

**Đáp án:** Cây rỗng, ví dụ biểu diễn bằng `root = null`. Không giữ nút gốc lá rỗng như một nút dữ liệu của cây không rỗng.

**Điểm ghi nhớ:** Xóa trong B-tree đòi hỏi giữ đủ khóa ở các nút. **Mượn khóa** từ anh em còn dư, thông qua khóa phân cách của cha; nếu không mượn được thì **gộp hai nút** cùng một khóa cha. Khi xóa khóa trong nút trong, dùng **tiền nhiệm**, **kế nhiệm** hoặc **gộp** tùy số khóa ở hai con. Sau cùng, nếu **gốc rỗng**, nâng con duy nhất làm gốc mới hoặc chuyển cây thành rỗng. Với bậc tối thiểu `t` cố định, quá trình đi và sửa một đường từ gốc tới lá vẫn có chi phí O(log n).
