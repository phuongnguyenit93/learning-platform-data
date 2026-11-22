# Kiểm tra trước khi đẩy bằng --dry-run và đối chiếu tham chiếu

Trước khi gửi commit lên repository từ xa, bạn nên xác định rõ **remote nào sẽ nhận dữ liệu, nhánh nào sẽ được cập nhật và những commit nào sẽ được gửi**. Git cung cấp `git push --dry-run` để mô phỏng một lần push: Git kết nối đến remote, tính toán các ref cần cập nhật và hiển thị kết quả dự kiến nhưng không thực hiện cập nhật ref trên máy chủ.

Lệnh chạy thử hữu ích khi bạn chuẩn bị push lên nhánh dùng chung, làm việc với nhiều remote hoặc dùng refspec tường minh. Tuy nhiên, kết quả dry-run chỉ phản ánh trạng thái remote tại thời điểm kiểm tra. Trạng thái remote có thể thay đổi trước lần push thật, và máy chủ vẫn có thể từ chối cập nhật vì quyền, chính sách nhánh hoặc kiểm tra phía server.

## 1. `git push --dry-run` làm gì?

Lệnh push thông thường gửi các đối tượng cần thiết lên remote rồi yêu cầu máy chủ cập nhật một hoặc nhiều ref. Với `--dry-run`, Git thực hiện quy trình chuẩn bị và báo các cập nhật dự kiến, nhưng không yêu cầu áp dụng những cập nhật đó lên remote.

Ví dụ:

```bash
# Mô phỏng push nhánh main lên nhánh main của origin
git push --dry-run origin main:refs/heads/main
```

Lệnh này cho biết Git dự định đẩy nhánh local `main` vào nhánh `main` trên remote `origin`. Nó không cập nhật nhánh `main` trên máy chủ.

Có thể thêm `--verbose` để xem thông tin chi tiết hơn hoặc `--porcelain` để nhận kết quả theo định dạng máy đọc được:

```bash
git push --dry-run --verbose origin main:refs/heads/main
git push --dry-run --porcelain origin main:refs/heads/main
```

`--porcelain` hữu ích khi kết quả được xử lý bằng script. Khi đọc bằng mắt, hãy chú ý remote đích, ref nguồn, ref đích và trạng thái Git báo cho từng ref. Cách trình bày cụ thể có thể khác nhau theo phiên bản Git và giao thức remote.

### Dry-run không phải là một lần push đã hoàn tất

Dry-run không cập nhật ref trên remote và không làm cho commit trở thành commit đã được chia sẻ. Lệnh vẫn cần truy cập remote nên có thể cần mạng và xác thực. Kết quả chạy thử cũng không bảo đảm lần push thật chắc chắn thành công: người khác có thể push trước bạn, quyền hoặc chính sách máy chủ có thể thay đổi, và các kiểm tra phía server có thể đưa ra kết quả khác ở lần cập nhật thật.

Dry-run cũng không đưa nội dung chưa commit lên remote. `git push` truyền các commit có thể truy cập từ ref nguồn; các chỉnh sửa mới chỉ nằm trong working tree hoặc staging area chưa thuộc commit sẽ không được gửi.

## 2. Hiểu các ref trước khi kiểm tra

Để đọc kết quả push, cần phân biệt ba loại tham chiếu:

| Loại ref | Ví dụ | Ý nghĩa |
|---|---|---|
| Nhánh local | `main`, `feature/login` | Tham chiếu trong repository local, trỏ đến commit bạn đang phát triển hoặc chuẩn bị gửi |
| Nhánh remote trên máy chủ | `refs/heads/main` | Tham chiếu thực tế trong repository từ xa |
| Remote-tracking branch | `origin/main` | Bản ghi local về trạng thái nhánh remote tại lần fetch gần nhất |

`origin/main` không tự cập nhật ngay khi người khác push lên máy chủ. Nó chỉ phản ánh thông tin local đã nhận được qua `git fetch` hoặc một thao tác cập nhật ref phù hợp. Vì thế, trước khi so sánh local với remote-tracking branch, hãy fetch remote tương ứng.

```bash
# Lấy trạng thái mới nhất và cập nhật remote-tracking refs
git fetch origin

# Xem các nhánh local
git branch

# Xem các nhánh remote-tracking
git branch -r

# Xem nhánh local đang theo dõi remote branch nào
git branch -vv
```

Fetch lấy dữ liệu và cập nhật các tham chiếu theo refspec đã cấu hình; nó không tự merge thay đổi vào nhánh local hiện tại và thông thường không sửa working tree.

## 3. Kiểm tra trạng thái làm việc và commit nguồn

Trước khi push, kiểm tra xem thay đổi đã được ghi vào commit hay chưa:

```bash
git status --short
git branch --show-current
git log -1 --oneline
```

Nếu `git status --short` hiển thị tệp đã sửa hoặc đã staged, những nội dung đó chưa được gửi chỉ vì bạn chạy `git push`. Hãy xem diff, stage đúng phần thay đổi và commit theo quy trình của dự án:

```bash
git diff
git diff --cached
git add src/login
git diff --cached
git commit -m "Add login validation"
```

Nếu đang ở detached HEAD, hãy xác định rõ commit cần gửi và cân nhắc tạo nhánh local để giữ tham chiếu dễ quản lý. Không nên dựa vào tên nhánh mặc định khi chưa xác nhận nhánh hiện tại.

## 4. Đối chiếu local với remote-tracking branch

Sau khi fetch, có thể so sánh hai đầu nhánh bằng `git rev-list`:

```bash
git rev-list --left-right --count origin/main...main
```

Kết quả gồm hai số:

- Số thứ nhất: commit chỉ có thể truy cập từ `origin/main`.
- Số thứ hai: commit chỉ có thể truy cập từ `main` local.

Ví dụ:

```text
2       3
```

Nghĩa là remote-tracking branch có hai commit chưa có trong `main` local, còn `main` local có ba commit chưa có trong `origin/main`. Hai nhánh đang phân kỳ; push thông thường có thể bị từ chối vì cập nhật không phải fast-forward.

Để xem cụ thể các commit ở mỗi phía:

```bash
# Commit có ở local main nhưng chưa có ở origin/main
git log --oneline origin/main..main

# Commit có ở origin/main nhưng chưa có ở local main
git log --oneline main..origin/main

# Xem đồ thị hai phía
git log --oneline --left-right --graph origin/main...main
```

Phạm vi `A..B` liệt kê commit có thể truy cập từ `B` nhưng không có trong tập commit có thể truy cập từ `A`. Phạm vi `A...B` kết hợp các commit chỉ thuộc một phía hoặc phía còn lại; với `--left-right`, Git đánh dấu mỗi commit theo phía tương ứng.

Nếu remote branch chưa tồn tại, sẽ không có `origin/feature/login` để so sánh. Hãy kiểm tra ref đích trực tiếp trên remote trước khi quyết định:

```bash
git ls-remote --heads origin refs/heads/feature/login
```

Nếu lệnh không trả về dòng nào cho ref chính xác này, remote hiện không công bố nhánh đó (hoặc tài khoản không được phép nhìn thấy ref). Nếu có kết quả, dòng trả về chứa object ID và tên ref, ví dụ:

```text
8f2a1c...    refs/heads/feature/login
```

`git ls-remote` truy vấn các ref được công bố bởi remote mà không cập nhật remote-tracking branch trong local. Nếu cần phân tích đồ thị commit đầy đủ, hãy fetch trước.

## 5. Kiểm tra khả năng cập nhật fast-forward

Với một nhánh đã tồn tại trên remote, push thông thường có thể cập nhật ref nếu commit đích hiện tại của remote là tổ tiên của commit nguồn local. Có thể kiểm tra quan hệ đó bằng `git merge-base --is-ancestor` sau khi fetch:

```bash
git merge-base --is-ancestor origin/main main
```

Nếu lệnh kết thúc với mã thoát `0`, `origin/main` là tổ tiên của `main`: cập nhật từ `origin/main` đến `main` có thể thực hiện theo kiểu fast-forward. Nếu mã thoát là `1`, quan hệ tổ tiên này không đúng; hãy xem đồ thị để phân biệt local đang thiếu commit remote hay hai nhánh đã phân kỳ. Các lỗi khác có thể cho mã thoát khác và cần được xử lý riêng.

Kiểm tra trực quan:

```bash
git log --oneline --left-right --graph origin/main...main
```

Đừng dùng `--force` chỉ vì lệnh kiểm tra cho thấy nhánh phân kỳ. Trước tiên hãy hiểu commit nào chỉ có ở remote và commit nào chỉ có ở local; tích hợp thay đổi theo chính sách của nhóm. Nếu buộc phải viết lại lịch sử của nhánh do bạn quản lý, cần cân nhắc `--force-with-lease` và phối hợp với những người cùng sử dụng nhánh.

## 6. Chạy thử với refspec tường minh

Một lệnh push có thể phụ thuộc vào cấu hình mặc định như `push.default`, upstream branch hoặc remote mặc định. Khi muốn kiểm tra chính xác đích đến, hãy ghi rõ refspec:

```bash
# Gửi nhánh local feature/login đến cùng tên nhánh trên origin
git push --dry-run origin feature/login:refs/heads/feature/login
```

Trong refspec `nguồn:đích`:

- `feature/login` là ref nguồn local được dùng để xác định commit cần gửi.
- `refs/heads/feature/login` là ref đích trên remote cần cập nhật.

Nếu muốn gửi commit tại `HEAD` hiện tại đến một nhánh remote cụ thể:

```bash
git push --dry-run origin HEAD:refs/heads/review/login-check
```

Lệnh trên dự kiến cập nhật nhánh `review/login-check` trên `origin` bằng commit hiện tại của `HEAD`. Cách viết này hữu ích khi nhánh nguồn và nhánh đích có tên khác nhau hoặc bạn muốn tránh phụ thuộc vào cấu hình push mặc định.

Nếu chỉ chạy:

```bash
git push --dry-run origin
```

Git chọn các ref cần đẩy theo refspec push và cấu hình mặc định hiện hành. Cách này tiện trong workflow đã cấu hình ổn định, nhưng khi kiểm tra lần đầu hoặc làm việc với nhiều remote, refspec tường minh giúp kết quả dễ đánh giá hơn.

## 7. Đọc kết quả dry-run

Kết quả phụ thuộc vào trạng thái local, trạng thái remote, refspec và phiên bản Git. Các thông báo thường gặp có ý nghĩa như sau:

| Dạng kết quả | Cách hiểu |
|---|---|
| `Everything up-to-date` | Không có cập nhật nào cần gửi cho refspec đã chọn. |
| `[new branch]` | Lệnh dự kiến tạo một nhánh mới trên remote. |
| Một nhánh được liệt kê là cập nhật | Git dự kiến cập nhật ref đích từ ref nguồn đã chỉ định. |
| `[rejected]` hoặc thông báo non-fast-forward | Cập nhật không được chấp nhận theo quy tắc push hiện tại; cần kiểm tra lịch sử và chính sách remote. |
| `error` khi kết nối hoặc xác thực | Git chưa thể hoàn tất bước kiểm tra với remote; kiểm tra URL, mạng và thông tin xác thực. |

Khi dùng `--porcelain`, đầu ra được định dạng để công cụ có thể phân tích trạng thái của từng ref. Không nên viết script dựa trên một câu thông báo tự do; nếu tự động hóa, hãy dựa vào định dạng porcelain và mã thoát của lệnh.

Dry-run chỉ cho biết cập nhật dự kiến tại thời điểm kiểm tra. Ví dụ, nếu một đồng đội push commit mới sau khi bạn chạy thử, lần push thật có thể bị từ chối dù dry-run trước đó không báo lỗi. Hãy fetch và kiểm tra lại nếu đã có khoảng thời gian đáng kể hoặc có hoạt động đồng thời trên nhánh.

## 8. Một quy trình pre-push hoàn chỉnh

Giả sử bạn đã hoàn thành nhánh `feature/login` và muốn đẩy nó lên `origin`. Có thể thực hiện theo trình tự sau:

```bash
# 1. Xác nhận working tree và nhánh hiện tại
git status --short
git branch --show-current

# 2. Xác nhận remote và URL push
git remote -v
git remote get-url --push origin

# 3. Cập nhật thông tin remote
git fetch origin

# 4. Xem các commit local sẽ gửi và commit remote còn thiếu ở local
git log --oneline origin/feature/login..feature/login
git log --oneline feature/login..origin/feature/login

# 5. Đếm commit riêng của từng phía
git rev-list --left-right --count origin/feature/login...feature/login

# 6. Mô phỏng chính xác ref sẽ được cập nhật
git push --dry-run --verbose origin feature/login:refs/heads/feature/login
```

Đọc lại kết quả trước khi push thật. Xác nhận remote là fork hoặc repository đích đúng, nhánh đích đúng, commit nguồn đã được review và không có thay đổi remote mới cần tích hợp.

Nếu kết quả phù hợp, thực hiện push thật với cùng refspec:

```bash
git push -u origin feature/login:refs/heads/feature/login
```

`-u` thiết lập upstream branch cho nhánh local sau khi push thành công. Nếu nhánh đã có upstream branch đúng, có thể không cần dùng lại tùy chọn này.

## 9. Những giới hạn và nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Dry-run chứng minh push thật chắc chắn thành công | Nó chỉ mô phỏng cập nhật theo trạng thái và điều kiện tại thời điểm kiểm tra; server có thể thay đổi hoặc từ chối lần push thật. |
| Dry-run cập nhật `origin/main` local | Không. Muốn cập nhật remote-tracking refs, dùng `git fetch origin`. |
| Dry-run gửi cả nội dung đang staged | Không. Push gửi commit được tham chiếu bởi ref nguồn; thay đổi chưa commit không thuộc ref đó. |
| `origin/main` luôn là trạng thái mới nhất trên server | Đây là bản ghi local ở lần fetch gần nhất; có thể đã cũ. |
| Không có dòng từ `git ls-remote` nghĩa là branch chắc chắn chưa tồn tại | Thường là remote không công bố ref phù hợp; quyền xem hoặc pattern cũng có thể ảnh hưởng kết quả. |
| Hai số từ `rev-list --left-right --count` là số tệp khác nhau | Đó là số commit chỉ có ở mỗi phía, không phải số tệp hoặc số dòng thay đổi. |
| Dry-run với remote mặc định luôn đẩy đúng nhánh mong muốn | Cấu hình push mặc định có thể chọn ref khác; dùng refspec tường minh khi cần kiểm soát. |

## 10. Tự kiểm tra

1. **`git push --dry-run` có cập nhật nhánh trên máy chủ không?**
   - Không. Nó báo các cập nhật dự kiến nhưng không thực hiện cập nhật ref trên remote.
2. **Vì sao nên chạy `git fetch origin` trước khi so sánh `origin/main` với `main`?**
   - Để cập nhật remote-tracking ref local theo trạng thái mới nhất mà remote công bố tại lần fetch đó.
3. **Trong kết quả `git rev-list --left-right --count origin/main...main`, số thứ hai biểu thị gì?**
   - Số commit chỉ có thể truy cập từ `main` local, thường là phần local đi trước remote.
4. **Lệnh nào kiểm tra remote có nhánh `feature/login` hay chưa mà không cập nhật remote-tracking refs?**
   - `git ls-remote --heads origin refs/heads/feature/login`.
5. **Vì sao nên dùng refspec tường minh trong lệnh dry-run?**
   - Để xác định rõ nhánh nguồn và ref đích, tránh nhầm do cấu hình push mặc định hoặc upstream branch.

## Kết luận

`git push --dry-run` giúp xem trước các ref mà Git dự định cập nhật trên remote. Để đánh giá kết quả có ý nghĩa, hãy kiểm tra working tree, xác định remote và ref đích, fetch để cập nhật remote-tracking refs, đối chiếu commit hai phía rồi chạy dry-run với refspec rõ ràng. Kết quả này là một bước kiểm tra hữu ích trước khi push; lần push thật vẫn cần được đánh giá theo trạng thái và chính sách của remote tại thời điểm thực hiện.
