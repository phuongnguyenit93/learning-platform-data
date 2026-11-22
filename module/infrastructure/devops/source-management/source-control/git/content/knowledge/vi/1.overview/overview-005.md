# Mô hình bản chụp, commit và đồ thị lịch sử

Git quản lý lịch sử mã nguồn bằng cách lưu các trạng thái đã được ghi nhận của dự án và liên kết những trạng thái đó thành một đồ thị. Để hiểu Git hoạt động ra sao, cần nắm ba khái niệm liên quan chặt chẽ: **bản chụp (snapshot)** mô tả nội dung của một phiên bản, **commit** ghi nhận một bản chụp cùng thông tin về nguồn gốc của nó, và **đồ thị lịch sử** thể hiện các commit nối tiếp hoặc phân nhánh như thế nào.

Những khái niệm này giải thích vì sao Git có thể so sánh phiên bản, tạo nhánh, hợp nhất công việc và khôi phục trạng thái cũ mà vẫn giữ được lịch sử phát triển của dự án.

## 1. Git lưu trạng thái dự án dưới dạng bản chụp

Hãy hình dung một dự án có ba tệp: `README.md`, `src/App.java` và `src/Utils.java`. Sau khi hoàn thành một phần công việc, ta muốn ghi nhận trạng thái của cả dự án tại thời điểm đó. Git tạo một bản chụp đại diện cho nội dung được quản lý ở thời điểm ghi nhận.

Trong cách mô hình hóa của Git, một commit trỏ đến một đối tượng **tree** ở thư mục gốc. Tree mô tả các mục trong thư mục: tệp, thư mục con, chế độ tệp và tham chiếu đến đối tượng chứa nội dung. Các tree con tiếp tục mô tả cấu trúc thư mục. Nội dung của một tệp thông thường được lưu trong đối tượng **blob**.

Ví dụ, cấu trúc khái niệm có thể trông như sau:

```text
commit C1
  |
  +-- tree (thư mục gốc)
        |
        +-- README.md ------> blob B1
        |
        +-- src ------------> tree T1
                               |
                               +-- App.java ---> blob B2
                               |
                               +-- Utils.java -> blob B3
```

Blob lưu nội dung tệp, không lưu tên tệp. Tree liên kết tên và thuộc tính của mục trong thư mục với blob hoặc tree tương ứng. Commit liên kết bản chụp ở cấp thư mục gốc với thông tin lịch sử như tác giả, người tạo commit, thời điểm, thông điệp và commit cha.

### Bản chụp khác với một bản vá

Khi xem lịch sử, ta thường thấy Git trình bày phần thêm, sửa và xóa giữa hai phiên bản. Cách trình bày đó dễ khiến người mới nghĩ rằng mỗi commit chỉ lưu một bản vá so với commit trước. Về mặt mô hình dữ liệu, commit của Git trỏ đến một bản chụp cây thư mục hoàn chỉnh.

Git có thể tái sử dụng các đối tượng nội dung và tree không thay đổi. Nếu một tệp giữ nguyên nội dung, Git không cần tạo một blob mới chỉ vì ta tạo commit tiếp theo. Nếu một thư mục không đổi, tree tương ứng cũng có thể được dùng lại. Nhờ vậy, việc mỗi commit đại diện cho toàn bộ trạng thái không có nghĩa Git phải nhân bản toàn bộ dữ liệu ở mỗi lần commit.

Khi hiển thị khác biệt, Git so sánh hai trạng thái để suy ra những thay đổi cần trình bày. Diff là cách diễn giải sự khác nhau giữa các bản chụp; nó không phải toàn bộ mô hình lưu trữ của commit.

## 2. Ba vùng trạng thái cần phân biệt

Trước khi tạo commit, Git cho phép chuẩn bị chính xác những thay đổi sẽ được ghi nhận. Quy trình này được hiểu dễ hơn khi phân biệt ba vùng:

| Vùng | Vai trò | Cách quan sát |
|---|---|---|
| Working tree | Các tệp và thư mục đang có trong thư mục làm việc | `git status`, xem trực tiếp tệp |
| Staging area (index) | Bản nội dung đã chọn để đưa vào commit kế tiếp | `git diff --cached`, `git ls-files --stage` |
| Repository và `HEAD` | Các đối tượng đã được lưu cùng vị trí commit hiện tại | `git log`, `git show`, `git cat-file` |

Có thể hình dung luồng cơ bản như sau:

```text
Working tree
   |  git add
   v
Staging area (index)
   |  git commit
   v
Commit mới trong repository
   |
   +---- HEAD của nhánh hiện tại được cập nhật
```

Working tree là nơi bạn chỉnh sửa mã nguồn. Khi chạy `git add`, Git lấy nội dung tại thời điểm đó để cập nhật index. Index vì thế là bản chuẩn bị cho commit tiếp theo. Nếu bạn tiếp tục sửa tệp sau khi `git add`, phần sửa mới nằm trong working tree và chưa tự động trở thành nội dung đã staged.

Ví dụ:

```bash
# Xem trạng thái hiện tại
git status

# Đưa một tệp vào vùng staging
git add src/App.java

# Xem phần đã staged, tức nội dung dự kiến được commit
git diff --cached

# Xem phần đang sửa nhưng chưa staged
git diff

# Ghi nhận nội dung trong staging area
git commit -m "Add application entry point"
```

Lệnh `git diff` mặc định so sánh working tree với index. Lệnh `git diff --cached` (tương đương `git diff --staged`) so sánh index với commit được tham chiếu bởi `HEAD`. Hai lệnh trả lời hai câu hỏi khác nhau: phần nào còn chưa được đưa vào staging, và phần nào đã sẵn sàng đi vào commit.

## 3. Commit là một đối tượng ghi nhận bản chụp

Một commit thông thường chứa các thông tin chính:

- **Tree**: bản chụp ở thư mục gốc mà commit ghi nhận.
- **Parent**: một hoặc nhiều commit cha, cho biết commit này nối vào lịch sử nào.
- **Author**: người được ghi nhận là tác giả của thay đổi.
- **Committer**: người hoặc tiến trình tạo đối tượng commit.
- **Timestamp**: thời điểm tương ứng của author và committer.
- **Message**: thông điệp giải thích mục đích của commit.

Commit không chứa nguyên văn toàn bộ mã nguồn trong một khối. Nó chứa tham chiếu đến tree và các thông tin lịch sử; tree lần lượt tham chiếu đến các blob và tree con.

Một commit được định danh bằng mã băm của nội dung đối tượng. Mã băm đầy đủ thường được gọi là object ID (OID). Khi nội dung commit thay đổi, OID của đối tượng cũng thay đổi. Vì commit chứa tham chiếu đến tree và parent, OID của commit phản ánh cả trạng thái dự án được ghi nhận lẫn vị trí của nó trong lịch sử.

### Commit cha tạo nên quan hệ lịch sử

Với commit thông thường, có một commit cha. Commit đầu tiên trong một repository mới thường không có parent. Commit merge có từ hai parent trở lên vì nó kết nối các dòng lịch sử đã phân nhánh.

Ví dụ một chuỗi commit tuyến tính:

```text
C1 ----> C2 ----> C3
```

Mũi tên trong sơ đồ biểu thị quan hệ từ commit cũ đến commit mới. Nói theo trường `parent` được lưu trong commit, `C3` trỏ về `C2`, còn `C2` trỏ về `C1`.

Commit đã được tạo thường được xem là bất biến. Nếu muốn thay đổi nội dung đã commit, Git tạo một đối tượng commit mới với OID mới. Các thao tác như amend hoặc rebase có thể tạo lại commit, vì vậy mã commit có thể thay đổi dù nội dung mã nguồn nhìn thấy có vẻ tương tự.

## 4. Đồ thị lịch sử là gì?

Vì mỗi commit tham chiếu đến commit cha, toàn bộ lịch sử hình thành một **đồ thị có hướng không chu trình** (directed acyclic graph, DAG). Mỗi đỉnh là một commit; quan hệ parent nối commit mới với commit trước đó. Nhánh phát triển độc lập tạo ra nhiều đường đi, và merge có thể nối các đường đó lại.

Một ví dụ có nhánh tính năng:

```text
             C2 ---- C3
            /          \
C1 --------+------------ M ---- C5
            \          /
             F1 ------
```

Trong sơ đồ này:

- `C1` là commit chung ban đầu.
- `C2` và `C3` tiếp tục dòng lịch sử chính.
- `F1` là commit được tạo trên nhánh tính năng từ `C1`.
- `M` là commit merge kết nối hai dòng lịch sử; nó có hai parent.
- `C5` được tạo sau merge.

Sơ đồ chỉ minh họa quan hệ cha-con. Vị trí trái-phải hoặc trên-dưới không biểu diễn thời lượng hay mức độ quan trọng của thay đổi.

### Nhánh và HEAD là các tham chiếu

Tên nhánh như `main` hoặc `feature/login` không phải bản sao của toàn bộ thư mục. Một nhánh là một tham chiếu có thể di chuyển, thường trỏ đến commit mới nhất của dòng phát triển đó. Khi tạo commit trên nhánh đang được checkout, tham chiếu nhánh được cập nhật để trỏ đến commit mới.

`HEAD` cho biết vị trí hiện tại của repository. Thông thường, `HEAD` trỏ gián tiếp thông qua tên nhánh đang checkout. Trường hợp đó được gọi là **attached HEAD**. Nếu checkout trực tiếp một mã commit thay vì một nhánh, `HEAD` trỏ thẳng đến commit và repository ở trạng thái **detached HEAD**.

Ví dụ:

```bash
# Xem commit mà HEAD đang tham chiếu
git log -1 --oneline

# Xem các nhánh và commit mà chúng đang trỏ tới
git branch -v

# Xem HEAD và các tham chiếu liên quan
git show-ref --head

# Xem lịch sử dưới dạng đồ thị
git log --oneline --graph --decorate --all
```

`git log --graph` vẽ các đường nối giữa commit để dễ nhận ra nhánh và merge. `--decorate` hiển thị tên tham chiếu như nhánh hoặc tag cạnh commit. `--all` yêu cầu Git hiển thị lịch sử có thể truy cập từ tất cả tham chiếu được chọn, thay vì chỉ từ `HEAD`.

## 5. Từ thay đổi đến commit: một ví dụ hoàn chỉnh

Giả sử bạn đang ở nhánh `main` và muốn thêm một tiện ích vào dự án.

```bash
# Kiểm tra vị trí và trạng thái
git branch --show-current
git status

# Tạo hoặc chỉnh sửa src/Utils.java trong working tree

# Đưa thay đổi cần ghi nhận vào index
git add src/Utils.java

# Kiểm tra chính xác nội dung sắp commit
git diff --cached

# Tạo commit
git commit -m "Add string utility"

# Kiểm tra commit mới và quan hệ với commit trước
git show --stat --oneline HEAD
git log --oneline --graph --decorate -5
```

Sau lệnh `git add`, index chứa nội dung được chọn của `src/Utils.java`. Khi chạy `git commit`, Git tạo blob/tree cần thiết, tạo đối tượng commit trỏ đến tree đó và commit cha hiện tại, rồi cập nhật nhánh đang checkout. `HEAD` tiếp tục xác định vị trí hiện tại thông qua nhánh đó.

Lưu ý: dòng chú thích “Tạo hoặc chỉnh sửa” trong ví dụ là thao tác thực hiện bằng trình soạn thảo; Git không tạo nội dung tệp chỉ vì chạy `git status` hay `git add`.

## 6. Đọc và kiểm tra các đối tượng Git

Các lệnh sau giúp quan sát cấu trúc dữ liệu mà những lệnh thông thường sử dụng:

```bash
# Hiển thị loại đối tượng mà một tham chiếu phân giải tới
git cat-file -t HEAD

# Hiển thị nội dung đối tượng commit
git cat-file -p HEAD

# Hiển thị tree được commit hiện tại tham chiếu
git ls-tree HEAD

# Hiển thị thông tin commit cùng diff của nó
git show HEAD

# Xem danh sách commit theo dạng rút gọn
git log --oneline --decorate
```

`git cat-file -p HEAD` thường cho thấy các dòng `tree`, `parent`, `author`, `committer` và thông điệp commit. `git ls-tree HEAD` cho thấy các mục trực tiếp trong tree gốc. Muốn xem tree con, có thể dùng OID của tree đó hoặc chỉ định đường dẫn phù hợp với lệnh.

Để so sánh hai bản chụp:

```bash
# So sánh trạng thái của hai commit
git diff <commit-cu> <commit-moi>

# Chỉ xem tên các tệp khác nhau
git diff --name-status <commit-cu> <commit-moi>

# Xem các commit có thể truy cập từ HEAD
git log --oneline HEAD
```

Thay `<commit-cu>` và `<commit-moi>` bằng mã commit, tag hoặc tham chiếu hợp lệ. Lệnh `git diff A B` trình bày khác biệt giữa hai trạng thái được tham chiếu; nó không sửa đổi hai commit đó.

## 7. Vì sao mô hình này hữu ích?

**Theo dõi thay đổi:** Mỗi commit cung cấp một điểm tham chiếu ổn định cho trạng thái dự án. Có thể so sánh hai commit để tìm nội dung được thêm, sửa hoặc xóa.

**Làm việc song song:** Các nhánh cho phép nhiều hướng phát triển cùng xuất phát từ một commit chung. Đồ thị lưu lại mối quan hệ giữa các hướng đó.

**Hợp nhất có căn cứ:** Merge tạo commit có nhiều parent để ghi nhận việc kết nối các lịch sử. Git dùng quan hệ tổ tiên và nội dung các bản chụp để tính toán kết quả hợp nhất.

**Truy tìm nguyên nhân:** Khi một lỗi xuất hiện, lịch sử commit và diff giúp xác định thay đổi nào đã đưa hành vi mới vào dự án. Những công cụ như `git log`, `git show` và `git blame` khai thác dữ liệu lịch sử này.

**Khôi phục có kiểm soát:** Vì commit tham chiếu đến bản chụp và các commit cha, ta có thể tạo commit mới để đảo ngược một thay đổi hoặc chuyển working tree đến trạng thái đã ghi nhận trước đó. Việc chọn lệnh khôi phục cần xét xem thay đổi đã commit, đã staged hay vẫn chỉ nằm trong working tree.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Commit chỉ lưu phần diff so với commit trước | Commit trỏ đến tree đại diện cho trạng thái dự án; diff được tính khi cần so sánh. |
| `git add` tạo commit | `git add` cập nhật index; `git commit` mới tạo đối tượng commit. |
| Staging area là một thư mục tạm chứa bản sao tệp | Index là cấu trúc dữ liệu ghi nhận nội dung và metadata đã chọn cho commit kế tiếp. |
| Nhánh là một bản sao thư mục | Nhánh là tham chiếu di động đến một commit. |
| Merge luôn tạo đúng một commit | Fast-forward có thể chỉ di chuyển tham chiếu; merge commit được tạo trong những trường hợp phù hợp và có thể có nhiều parent. |
| Mã commit chỉ đại diện cho nội dung tệp | OID commit được tính từ nội dung đối tượng commit, trong đó có tham chiếu tree và parent cùng metadata. |
| Diff là dữ liệu duy nhất Git dùng để hiểu lịch sử | Diff là cách trình bày khác biệt giữa các trạng thái; quan hệ lịch sử được mô tả qua các commit và parent. |

## 9. Tự kiểm tra

1. **Một commit thông thường trỏ đến đối tượng nào để mô tả trạng thái dự án?**
   - Đối tượng tree ở thư mục gốc.
2. **Sau khi sửa tệp và chạy `git add`, nội dung được chuẩn bị nằm ở đâu?**
   - Trong staging area (index). Nếu tiếp tục sửa tệp, phần sửa mới chưa tự động được staged.
3. **Vì sao có thể nói lịch sử Git là một DAG?**
   - Commit mới tham chiếu đến commit cha; các quan hệ này tạo thành đồ thị có hướng và không có chu trình.
4. **Một merge commit thường khác commit thông thường ở điểm nào?**
   - Nó có từ hai parent trở lên, thể hiện việc kết nối các dòng lịch sử.
5. **Tên nhánh `main` có lưu toàn bộ nội dung dự án không?**
   - Không. Nó là một tham chiếu đến commit hiện tại của dòng phát triển đó.

## Kết luận

Mô hình bản chụp giải thích cách Git biểu diễn trạng thái dự án; commit gắn bản chụp với metadata và commit cha; các quan hệ cha-con kết hợp thành đồ thị lịch sử. Khi phân biệt được working tree, index, commit và tham chiếu nhánh, bạn sẽ hiểu rõ hơn điều gì xảy ra sau mỗi lệnh `git add`, `git commit`, `git branch` hoặc `git merge`, đồng thời đọc lịch sử dự án một cách chủ động.
