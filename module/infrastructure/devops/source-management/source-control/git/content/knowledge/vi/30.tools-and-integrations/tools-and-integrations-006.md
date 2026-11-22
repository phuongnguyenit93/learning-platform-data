# Checkout trong môi trường tự động: detached HEAD và lịch sử nông

Trong pipeline CI/CD, Git thường checkout đúng một commit để build, chạy test hoặc tạo artifact. Vì checkout theo mã commit không nhất thiết gắn với một branch local, repository có thể ở trạng thái **detached HEAD**. Nhiều pipeline cũng dùng **shallow clone** để tải ít lịch sử hơn và rút ngắn thời gian checkout.

Hai trạng thái này có mục đích khác nhau: detached HEAD mô tả cách HEAD trỏ tới commit; shallow clone mô tả phần lịch sử đã được tải về. Chúng có thể xuất hiện cùng lúc hoặc độc lập. Hiểu rõ chúng giúp bạn tái tạo đúng mã nguồn cần kiểm thử, tránh giả định branch đang tồn tại và biết khi nào phải tải thêm lịch sử để tạo changelog, tính version hoặc thực hiện merge/rebase.

## 1. Vì sao môi trường tự động thường checkout một commit?

Một pipeline thường được kích hoạt bởi một sự kiện cụ thể: push lên branch, tạo tag, mở pull request hoặc chạy theo lịch. Tại thời điểm pipeline bắt đầu, hệ thống xác định một commit cần kiểm tra.

Ví dụ:

```text
main:       A --- B --- C
                         \
feature:                  D --- E

Pipeline được yêu cầu kiểm tra commit E
```

Pipeline có thể lấy commit E trực tiếp và checkout nó. Mục tiêu là build đúng snapshot được yêu cầu, ngay cả khi branch sau đó tiếp tục di chuyển tới commit mới.

Dùng commit ID giúp kết quả có thể truy vết:

```bash
git rev-parse HEAD
git show -s --format=fuller HEAD
```

Hai lệnh cho biết OID và metadata của commit thực tế đang được checkout. Khi lưu log build, ghi lại OID này giúp đối chiếu artifact với source commit.

Trong pull request, commit được kiểm tra có thể là commit đầu nhánh của người đóng góp hoặc một commit merge tạm do nền tảng CI tạo ra để mô phỏng kết quả hợp nhất với branch đích. Không nên mặc định mọi pipeline pull request đều build cùng một loại commit. Hãy xem cấu hình checkout của pipeline và ghi nhận OID thực tế bằng `git rev-parse HEAD`.

## 2. Detached HEAD là gì?

Ở trạng thái thông thường, `HEAD` là symbolic ref trỏ tới branch hiện tại:

```text
HEAD -> refs/heads/main -> commit C
```

Khi checkout trực tiếp một commit, tag hoặc remote-tracking ref, Git có thể chuyển sang detached HEAD:

```text
HEAD --------------------> commit E

refs/heads/main ----------> commit C
refs/heads/feature -------> commit E
```

`HEAD` trỏ thẳng tới commit E, không thông qua một branch local. Đây là trạng thái hợp lệ và thường gặp trong CI.

Ví dụ:

```bash
git checkout --detach <commit-oid>
```

Hoặc dùng lệnh `switch` hiện đại:

```bash
git switch --detach <commit-oid>
```

Checkout tag cũng thường dẫn tới detached HEAD:

```bash
git switch --detach v2.4.0
```

Bạn vẫn có thể đọc file, chạy build, test, lint và tạo artifact. Detached HEAD không làm repository thành read-only. Điểm cần lưu ý là nếu tạo commit mới khi detached, commit đó không tự động được gắn vào branch nào.

Kiểm tra trạng thái:

```bash
git status --short --branch
git branch --show-current
git rev-parse --short HEAD
git symbolic-ref -q --short HEAD
```

Khi detached HEAD:

- `git status --short --branch` thường hiển thị phần đầu `## HEAD (no branch)`; dạng đầy đủ của `git status` có thể ghi `HEAD detached at ...`.
- `git branch --show-current` trả về chuỗi rỗng vì không có branch local hiện tại.
- `git rev-parse HEAD` vẫn trả về OID commit.
- `git symbolic-ref` không phân giải được `HEAD` thành branch và trả mã thoát khác 0.

Đừng dùng kết quả rỗng của `git branch --show-current` để kết luận checkout bị lỗi. Hãy kiểm tra `git status` và `git rev-parse HEAD`.

## 3. Detached HEAD và shallow clone là hai khái niệm độc lập

Detached HEAD mô tả vị trí của `HEAD`; shallow clone mô tả độ sâu lịch sử hiện có trong repository.

| Tình huống | HEAD | Lịch sử |
|---|---|---|
| Checkout branch đầy đủ | Trỏ qua branch | Có lịch sử đã fetch theo ref |
| Checkout commit trong clone đầy đủ | Trỏ trực tiếp tới commit | Có lịch sử đầy đủ đã lấy |
| Checkout commit trong shallow clone | Trỏ trực tiếp tới commit | Chỉ có một phần lịch sử |
| Checkout branch trong shallow clone | Trỏ qua branch | Branch chỉ có lịch sử nông đã fetch |

Có thể kiểm tra riêng hai trạng thái:

```bash
git status --short --branch
git rev-parse --is-shallow-repository
```

Lệnh đầu cho biết HEAD đang attached hay detached. Lệnh thứ hai in `true` nếu repository là shallow, `false` nếu không.

Vì hai trạng thái độc lập, việc tạo branch mới từ detached HEAD không tự tải thêm lịch sử. Tương tự, tải thêm lịch sử không tự chuyển HEAD về branch.

## 4. Tạo shallow clone để checkout nhanh

Shallow clone chỉ tải một phần lịch sử thay vì toàn bộ ancestry của branch. Cách đơn giản nhất:

```bash
git clone --depth 1 https://example.com/team/app.git
```

`--depth 1` yêu cầu lịch sử nông với một commit ở đầu branch được lấy. Khi dùng `--depth`, Git mặc định cũng giới hạn việc lấy lịch sử vào một branch (tương đương hành vi `--single-branch`), trừ khi chỉ định `--no-single-branch`.

Có thể chỉ rõ branch:

```bash
git clone --depth 1 --branch main --single-branch https://example.com/team/app.git
```

Lệnh này lấy branch `main` với độ sâu 1. Nó phù hợp khi pipeline chỉ cần snapshot hiện tại để build hoặc test và không cần truy vấn lịch sử xa hơn.

Sau khi clone, kiểm tra:

```bash
cd app
git rev-parse --is-shallow-repository
git log --oneline --decorate
git status --short --branch
```

Repository shallow vẫn chứa commit được checkout và các object cần thiết để tái tạo snapshot của commit đó. Tuy nhiên, commit cha nằm ngoài ranh giới shallow có thể chưa có trong object database.

Shallow clone không có nghĩa Git tải file thiếu hoặc source code bị cắt bớt. Nó giới hạn lịch sử commit được lấy; snapshot của commit đã checkout vẫn có thể được sử dụng bình thường.

## 5. Checkout một commit cụ thể trong CI

Trong pipeline, nên checkout đúng ref hoặc commit mà sự kiện yêu cầu. Quy trình tổng quát:

1. Lấy repository và các ref cần thiết.
2. Xác định OID của commit cần build.
3. Checkout OID đó ở detached HEAD.
4. Ghi lại OID và trạng thái repository.
5. Chạy build/test trên snapshot đã chọn.

Ví dụ với repository đã được clone:

```bash
git fetch origin
git checkout --detach <commit-oid>
git rev-parse HEAD
git status --short --branch
```

Nếu pipeline chỉ cần một commit và server hỗ trợ fetch theo refspec cụ thể, có thể tải ref cần thiết với độ sâu nhỏ:

```bash
git fetch --depth=1 origin <refspec>
git checkout --detach FETCH_HEAD
```

`<refspec>` phải là ref mà remote cho phép fetch, chẳng hạn branch hoặc ref pull request do hệ thống CI cung cấp. Không phải server nào cũng cho phép fetch trực tiếp một OID tùy ý. Nếu fetch thất bại, hãy fetch ref chứa commit đó rồi checkout OID tương ứng.

Sau khi checkout, xác minh `HEAD` đúng với commit pipeline yêu cầu:

```bash
git rev-parse HEAD
git show -s --format='%H %s' HEAD
```

Không chỉ dựa vào tên branch trong log pipeline: branch có thể được cập nhật trong khi job chạy, còn OID là định danh commit cụ thể.

## 6. Khi nào cần tạo branch từ detached HEAD?

Phần lớn pipeline chỉ đọc source, build và test. Với các công việc này, detached HEAD là phù hợp; không cần tạo branch local.

Bạn cần branch nếu pipeline phải tạo commit mới và muốn giữ commit đó bằng một ref có tên, ví dụ:

- Tạo commit cập nhật version hoặc changelog.
- Sinh file được quản lý bằng Git và commit kết quả.
- Chạy một bước sửa mã tự động rồi tạo commit để review.
- Chuẩn bị branch tạm để push kết quả lên remote.

Tạo branch từ commit hiện tại:

```bash
git switch -c ci/update-generated-files
```

Hoặc dùng lệnh checkout tương đương:

```bash
git checkout -b ci/update-generated-files
```

Sau đó có thể stage và commit:

```bash
git add -- CHANGELOG.md
git commit -m "Update generated changelog"
```

Branch mới giữ commit vừa tạo. Nếu chỉ tạo commit khi detached rồi chuyển sang một commit khác, commit đó có thể không còn được tham chiếu bởi branch và về sau bị garbage collection dọn nếu không có ref nào khác giữ nó.

Trong CI chạy song song, tên branch tạm cần tránh xung đột giữa các job. Nếu branch đích đã tồn tại, `git switch -c` sẽ từ chối tạo lại. Hãy dùng tên duy nhất theo mã job hoặc run ID do hệ thống cung cấp, đồng thời xác minh quyền push trước khi thực hiện.

Nếu pipeline không cần chia sẻ commit, không cần tạo branch chỉ để làm cho `git status` hiển thị tên branch.

## 7. Push kết quả từ pipeline

Nếu pipeline đã tạo branch và cần chia sẻ commit, push ref cụ thể:

```bash
git push origin HEAD:refs/heads/ci/update-generated-files
```

Phần bên trái `HEAD` là commit hiện tại; phần bên phải là branch đích trên remote. Cách viết refspec đầy đủ giúp tránh nhầm lẫn giữa branch local và remote.

Trước khi push, kiểm tra:

```bash
git status
git log -1 --oneline
git remote -v
```

Pipeline cũng cần quyền xác thực và quyền ghi phù hợp. Nhiều job CI chỉ được cấp quyền đọc repository; việc tạo commit local vẫn có thể thành công nhưng push sẽ bị từ chối.

Không nên dùng `git push --force` như cách mặc định để giải quyết lỗi push từ pipeline. Nếu branch đích đã thay đổi, fetch và kiểm tra lịch sử trước khi quyết định cách tích hợp.

Nếu commit chỉ phục vụ build/test, thường không cần push branch tạm. Hãy để artifact và log build tham chiếu tới OID nguồn thay vì tạo thêm nhánh không cần thiết.

## 8. Vì sao lịch sử nông làm một số lệnh cho kết quả thiếu?

Trong shallow clone, Git có thể biết commit hiện tại nhưng không biết toàn bộ commit cha của nó. Ranh giới shallow được đánh dấu trong metadata repository. Git coi các commit tại ranh giới đó như điểm bắt đầu của lịch sử cục bộ hiện có.

Điều này ảnh hưởng các thao tác cần đi ngược lịch sử:

| Nhu cầu | Ảnh hưởng có thể gặp trong shallow clone |
|---|---|
| Xem log dài | `git log` chỉ hiển thị phần commit đã tải |
| Tính số commit từ gốc | `git rev-list --count` có thể đếm thiếu |
| Tìm merge base | Có thể không tìm thấy ancestor vì lịch sử cần thiết chưa được tải |
| Tạo changelog | Có thể bỏ sót commit kể từ tag hoặc mốc phát hành |
| `git describe` | Không tìm thấy tag cũ nằm ngoài phần lịch sử đã lấy |
| `git blame` | Không lần ngược tới commit gốc của dòng nếu ancestry thiếu |
| Merge/rebase | Một số thao tác có thể bị giới hạn hoặc cần thêm lịch sử |

Ví dụ, lệnh:

```bash
git log --oneline --all
```

chỉ hiển thị các commit reachable từ refs hiện có và object đã tải. Nó không thể hiển thị commit chưa được fetch.

Nếu lệnh:

```bash
git merge-base origin/main HEAD
```

không in OID, đừng kết luận ngay hai nhánh không có tổ tiên chung. Trong shallow repository, commit chung có thể nằm ngoài ranh giới lịch sử hiện có. Hãy kiểm tra shallow state và tải thêm lịch sử cần thiết.

## 9. Tải thêm lịch sử bằng deepen

Nếu chỉ cần thêm một phần lịch sử, dùng `git fetch --deepen`:

```bash
git fetch --deepen=50 origin main
```

Lệnh yêu cầu lấy thêm 50 commit từ ranh giới shallow hiện tại cho branch `main`. Nó hữu ích khi pipeline ban đầu chỉ tải rất ít commit nhưng bước sau cần thêm lịch sử để tính changelog hoặc so sánh với commit nền.

Một cách khác là chỉ định độ sâu mới tính từ đầu branch:

```bash
git fetch --depth=100 origin main
```

`--depth=100` yêu cầu lịch sử với độ sâu 100 commit tính từ tip được fetch. Khác với `--deepen=100`, vốn bổ sung số commit vào phần lịch sử nông hiện tại.

Có thể tải lịch sử theo mốc thời gian:

```bash
git fetch --shallow-since="2026-01-01" origin main
```

Hoặc loại trừ lịch sử reachable từ một ref:

```bash
git fetch --shallow-exclude=refs/tags/v1.0.0 origin main
```

Các tùy chọn này phù hợp khi pipeline chỉ cần đủ lịch sử cho một tác vụ nhất định. Sau khi fetch, kiểm tra lại:

```bash
git rev-parse --is-shallow-repository
git log --oneline --decorate -20
```

Repository có thể vẫn là shallow sau khi deepen. Điều đó bình thường nếu bạn chỉ tăng độ sâu một phần.

## 10. Chuyển shallow repository thành đầy đủ lịch sử

Nếu pipeline cần toàn bộ ancestry của các ref được fetch, dùng:

```bash
git fetch --unshallow origin
```

Lệnh này yêu cầu lấy phần lịch sử còn thiếu để chuyển repository shallow thành repository đầy đủ, nếu remote có lịch sử đầy đủ và refspec cần thiết được fetch. Nếu remote cũng là shallow hoặc server không cung cấp phần lịch sử cần thiết, việc unshallow có thể không hoàn tất như mong muốn.

Kiểm tra kết quả:

```bash
git rev-parse --is-shallow-repository
```

Kết quả `false` cho biết repository không còn ở trạng thái shallow.

Nếu clone ban đầu chỉ lấy một branch, hãy chú ý refspec fetch. Unshallow lịch sử của branch đang lấy không đồng nghĩa tự động có mọi branch remote khác trong local. Khi cần nhiều branch, fetch thêm các ref tương ứng hoặc cấu hình refspec rõ ràng.

Nếu cần tags và lịch sử gắn với tag, có thể fetch tags:

```bash
git fetch --tags origin
```

Tuy nhiên, fetch tag riêng không phải là cách thay thế cho việc deepen/unshallow khi cần ancestry đầy đủ. Tag có thể được tải nhưng commit cha cần để so sánh vẫn nằm ngoài ranh giới shallow.

## 11. Shallow clone không giống partial clone

Cả shallow clone và partial clone đều giúp giảm dữ liệu tải về, nhưng giới hạn khác nhau:

| Cơ chế | Giới hạn gì? | Ví dụ |
|---|---|---|
| Shallow clone | Độ sâu lịch sử commit | `git clone --depth 1 <url>` |
| Partial clone | Loại object được tải ngay; object có thể được lấy khi cần | `git clone --filter=blob:none <url>` |

Shallow clone cắt lịch sử ở một ranh giới commit. Partial clone có thể giữ quan hệ commit/tree nhưng trì hoãn tải một số object như blob. Hai cơ chế có thể được kết hợp nếu server hỗ trợ.

Không nên dùng `--filter=blob:none` để giải quyết lỗi thiếu ancestor do shallow history; nó xử lý vấn đề object payload, không mở rộng lịch sử commit. Tương tự, `--unshallow` không đồng nghĩa tải mọi blob ngay lập tức trong một partial clone.

## 12. Tags, version và changelog trong CI

Nhiều pipeline cần tính version dựa trên tag gần nhất, ví dụ `git describe`. Với shallow clone, tag hoặc commit được tag có thể chưa nằm trong phần lịch sử đã tải.

Kiểm tra tag có sẵn:

```bash
git tag --list
git describe --tags --always
```

Nếu pipeline không tìm thấy tag mong muốn, trước tiên fetch tags:

```bash
git fetch --tags origin
```

Sau đó kiểm tra lại:

```bash
git describe --tags --always
```

Nếu tag đã có nhưng commit tổ tiên cần để xác định khoảng cách vẫn nằm ngoài shallow boundary, hãy deepen hoặc unshallow lịch sử của branch liên quan.

Ví dụ tạo changelog từ tag phát hành gần nhất tới HEAD:

```bash
git log --oneline v2.3.0..HEAD
```

Lệnh chỉ đáng tin nếu tag `v2.3.0` và các commit cần thiết đã có trong repository, đồng thời phạm vi lịch sử phù hợp với branch đang build. Trong pipeline phát hành, hãy xác định tag nền rõ ràng thay vì dựa vào một tag gần nhất có thể thay đổi theo tập refs đã fetch.

## 13. Ví dụ pipeline: build nhanh và pipeline cần lịch sử

**Pipeline build/test thông thường**

Nếu chỉ cần kiểm tra snapshot được yêu cầu, shallow checkout thường đủ:

```bash
git clone --depth 1 --branch main --single-branch https://example.com/team/app.git
cd app
git status --short --branch
git rev-parse HEAD
./gradlew test
```

Job chỉ cần source hiện tại và không thực hiện thao tác phụ thuộc vào lịch sử xa.

**Pipeline tạo changelog hoặc version**

Nếu cần so sánh với tag phát hành hoặc tính số commit:

```bash
git clone --depth 1 --branch main https://example.com/team/app.git
cd app

git fetch --tags origin
git fetch --unshallow origin

git describe --tags --always
git log --oneline v2.3.0..HEAD
```

Ở đây pipeline lấy tags và mở rộng lịch sử để các lệnh version/changelog có đủ dữ liệu. Nếu remote không có lịch sử đầy đủ hoặc branch/tag ref chưa được fetch, cần điều chỉnh refspec cho đúng.

**Pipeline cần tạo commit**

Nếu job phải tạo commit, hãy tạo branch từ commit đang checkout:

```bash
git switch -c "ci/generated-$CI_RUN_ID"
# Tạo hoặc cập nhật file
git add -- CHANGELOG.md
git commit -m "Update generated changelog"
git push origin "HEAD:refs/heads/ci/generated-$CI_RUN_ID"
```

`CI_RUN_ID` ở ví dụ là biến do hệ thống CI cung cấp; thay bằng biến thực tế của nền tảng. Tên branch phải duy nhất giữa các job. Pipeline cũng cần quyền ghi và nên kiểm tra diff trước khi commit để tránh đưa file không liên quan vào lịch sử.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `git branch --show-current` không in gì | HEAD đang detached | Dùng `git rev-parse HEAD`; chỉ tạo branch nếu cần giữ commit mới |
| `git log` chỉ có một vài commit | Clone dùng `--depth` | Kiểm tra `git rev-parse --is-shallow-repository`, rồi deepen nếu cần |
| `git merge-base` không tìm thấy ancestor | Commit chung nằm ngoài shallow boundary | Fetch thêm lịch sử hoặc unshallow |
| `git describe` không tìm thấy version tag | Tag hoặc lịch sử liên quan chưa được fetch | Fetch tags và mở rộng lịch sử |
| `git checkout <commit>` báo không tìm thấy object | Commit chưa có trong object database | Fetch ref chứa commit hoặc đúng refspec trước |
| Commit tạo trong CI không xuất hiện trên branch | Job đang detached HEAD và chưa tạo ref giữ commit | Tạo branch trước khi commit hoặc lưu OID bằng ref phù hợp |
| Push từ CI bị từ chối | Token/SSH key không có quyền ghi hoặc branch protection chặn | Kiểm tra quyền và quy tắc branch của remote |
| `--unshallow` không lấy được toàn bộ lịch sử | Remote cũng shallow, refspec chưa đúng hoặc server giới hạn | Kiểm tra remote và fetch ref cần thiết |
| Fetch tags xong nhưng changelog vẫn thiếu | Tag đã tải nhưng ancestry vẫn nông | Deepen hoặc unshallow branch liên quan |

## 15. Checklist thiết kế checkout cho CI

Trước khi chọn cấu hình checkout, hãy xác định:

1. Pipeline cần build branch tip, tag hay một commit SHA chính xác?
2. Với pull request, cần kiểm tra commit của contributor hay merge result?
3. Có cần tạo commit/branch trong job không, hay chỉ build và test?
4. Tác vụ có cần lịch sử đầy đủ để tính version, changelog, blame hoặc merge-base không?
5. Tags và các branch cần thiết đã được fetch chưa?
6. Nếu clone nông, độ sâu hiện tại đã đủ cho tác vụ chưa?
7. Log build có ghi lại OID thực tế của `HEAD` không?
8. Nếu tạo commit, branch/ref có giữ commit và remote có cấp quyền push không?

Đừng tải toàn bộ lịch sử cho mọi job nếu chỉ cần snapshot để test. Ngược lại, đừng giữ clone ở độ sâu 1 khi bước phát hành cần so sánh tag, đếm commit hoặc tìm merge base. Chọn độ sâu theo yêu cầu thật của pipeline và kiểm tra kết quả trước khi dựa vào lịch sử.

## Kết luận

Trong môi trường tự động, detached HEAD là trạng thái bình thường khi Git checkout một commit cụ thể; nó không ngăn build hoặc test. Chỉ tạo branch khi job cần giữ commit mới bằng một ref có tên. Shallow clone giới hạn lịch sử đã tải, giúp checkout nhanh nhưng có thể làm thiếu kết quả log, merge-base, describe, blame và changelog. Dùng `git rev-parse --is-shallow-repository` để kiểm tra, `git fetch --deepen` để lấy thêm một phần hoặc `git fetch --unshallow` khi cần đầy đủ lịch sử. Luôn ghi lại OID thực tế đã build và chọn phạm vi fetch phù hợp với nhiệm vụ của pipeline.
