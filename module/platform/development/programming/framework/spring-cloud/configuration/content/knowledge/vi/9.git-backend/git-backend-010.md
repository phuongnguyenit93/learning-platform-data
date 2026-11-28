# Dọn nhánh đã xóa và kiểm soát bản tham chiếu cũ

## 1. Vì sao cần dọn nhánh cũ?

Git repository dùng làm backend cho Spring Cloud Config thường có nhiều branch phục vụ phát triển, kiểm thử và phát hành cấu hình. Sau khi một nhánh hoàn thành công việc, nhóm có thể merge pull request rồi xóa branch trên Git server. Tuy nhiên, việc xóa branch ở remote không đồng nghĩa mọi bản sao local đều lập tức quên branch đó.

Config Server dùng JGit và giữ một working copy local của remote repository. Khi client yêu cầu một label là branch, server có thể checkout branch đó thành local branch trong working copy. Nếu branch bị xóa trên remote, local branch đã tạo vẫn có thể tồn tại và tiếp tục được dùng để trả cấu hình cho request sau. Điều này tạo ra một rủi ro: client yêu cầu label cũ vẫn nhận cấu hình từ branch đã bị xóa, dù nhóm vận hành nghĩ rằng branch đó không còn tồn tại.

Việc dọn nhánh cũ giúp:

- Tránh Config Server phục vụ cấu hình từ branch đã bị xóa trên remote.
- Giữ danh sách branch trong working copy của server đồng bộ với repository nguồn.
- Làm cho hành vi fallback giữa nhiều label dễ dự đoán hơn.
- Giảm nhầm lẫn khi điều tra vì một label cũ vẫn trả về cấu hình.
- Hỗ trợ quy trình quản trị vòng đời branch và phát hành cấu hình có kiểm soát.

## 2. Phân biệt remote branch, remote-tracking ref và local branch

Để hiểu đúng việc dọn dẹp, cần phân biệt các loại tham chiếu Git:

| Loại tham chiếu | Ví dụ | Ý nghĩa |
|---|---|---|
| Remote branch | `refs/heads/feature/new-timeout` | Branch thực sự tồn tại trong repository trên Git server. |
| Remote-tracking ref | `refs/remotes/origin/feature/new-timeout` | Bản ghi trong clone local về trạng thái branch trên remote tại lần fetch gần nhất. |
| Local branch | `refs/heads/feature/new-timeout` | Branch local trong working copy, có thể được checkout và giữ lại sau khi remote branch bị xóa. |
| Tag | `refs/tags/config-v2.1.0` | Tham chiếu đặt tên cho một revision; thường dùng để ghim cấu hình phát hành. |

Ví dụ, Git server có branch `feature/new-timeout`. Config Server fetch branch đó và tạo local branch để checkout khi client yêu cầu label tương ứng. Sau đó nhóm xóa branch trên Git server. Nếu server chưa fetch và chưa dọn local branch, working copy có thể vẫn giữ `feature/new-timeout`.

Một client có thể gửi danh sách label dự phòng, chẳng hạn `feature/new-timeout,main`. Nếu local branch cũ vẫn tồn tại, Config Server có thể lấy cấu hình từ branch cũ thay vì tiếp tục đến `main`. Vì thế, xóa branch trên remote mà không kiểm soát bản sao local có thể khiến kết quả cấu hình khác với kỳ vọng của nhóm vận hành.

## 3. Bật delete-untracked-branches trong Config Server

Spring Cloud Config cung cấp thuộc tính `spring.cloud.config.server.git.delete-untracked-branches` để xóa local branch khi branch tương ứng đã bị xóa khỏi remote. Giá trị mặc định được tài liệu Spring Cloud Config hiện hành ghi là `false`, vì vậy cần bật rõ ràng nếu muốn server tự dọn các local branch này.

Ví dụ cấu hình:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: ${CONFIG_REPO_URI}
          default-label: main
          delete-untracked-branches: true
```

Khi fetch phát hiện remote-tracking ref bị xóa, Config Server sẽ xóa local branch tương ứng khỏi working copy. Việc xóa local branch này được thực hiện cưỡng bức vì working copy của server là bản sao phục vụ đọc cấu hình, không phải nơi developer lưu công việc chưa commit.

Điều quan trọng:

- Thuộc tính này xóa branch trong bản clone local của Config Server.
- Nó không xóa branch trên Git server.
- Nó không thay thế quy trình merge và xóa branch trên remote.
- Nó không phải lệnh dọn toàn bộ thư mục cache hoặc xóa mọi Git object.
- Nó không tự xóa tag cũ.

Hãy bật thuộc tính trên đúng Git backend đang sử dụng và kiểm tra hành vi với phiên bản Spring Cloud Config của dự án. Với cấu hình nhiều repository, cần xác nhận các repository được chọn đều áp dụng chính sách mong muốn.

## 4. Khi nào Config Server phát hiện branch đã bị xóa?

Config Server chỉ biết remote branch đã bị xóa sau khi fetch được cập nhật từ remote. Thuộc tính `delete-untracked-branches` quyết định xử lý local branch sau khi fetch phát hiện ref bị xóa; nó không tự tạo ra một lần fetch ngay lập tức.

Có thể điều khiển tần suất fetch bằng `spring.cloud.config.server.git.refresh-rate`, đơn vị giây:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: ${CONFIG_REPO_URI}
          delete-untracked-branches: true
          refresh-rate: 0
```

Theo tài liệu Spring Cloud Config:

- `refresh-rate: 0` (mặc định) yêu cầu server fetch dữ liệu cấu hình từ Git mỗi khi có request.
- Giá trị dương giới hạn việc fetch theo khoảng thời gian tính bằng giây; thay đổi remote có thể chỉ được phát hiện ở lần refresh tiếp theo.
- Giá trị âm tắt việc refresh; khi đó server không tự phát hiện branch mới bị xóa qua cơ chế fetch thông thường.

Ví dụ, nếu đặt `refresh-rate: 60`, remote branch vừa bị xóa có thể vẫn còn trong local cache cho đến lần fetch tiếp theo. Nếu đặt giá trị âm, đừng kỳ vọng `delete-untracked-branches` tự dọn branch đã mất mà server chưa fetch lại.

Khi chọn refresh rate, cần cân bằng độ mới của cấu hình với số lần truy cập Git, độ trễ và khả năng chịu lỗi của backend. Chính sách dọn branch chỉ có tác dụng sau khi server quan sát được thay đổi remote.

## 5. Dọn remote-tracking refs trong clone Git thông thường

Developer cũng thường có clone local riêng. Trong clone đó, sau khi branch bị xóa ở Git server, remote-tracking ref như `origin/feature/old-config` có thể vẫn còn cho đến khi fetch với prune.

Kiểm tra các branch đang biết:

```bash
git branch -a
git branch -vv
```

Xem trước remote-tracking refs nào sẽ bị xóa:

```bash
git remote prune --dry-run origin
```

Fetch và prune remote-tracking refs đã stale:

```bash
git fetch --prune origin
```

Hoặc chỉ prune mà không fetch các thay đổi mới:

```bash
git remote prune origin
```

`git fetch --prune origin` cập nhật thông tin từ remote và xóa các remote-tracking refs không còn tương ứng với refs trên remote theo refspec. `git remote prune origin` chỉ thực hiện việc prune. Các lệnh này chạy trên clone mà developer đang thao tác; chúng không trực tiếp dọn working copy nội bộ của Config Server.

Nếu cần xóa branch local đã merge trong clone của developer, có thể dùng:

```bash
git branch -d feature/old-config
```

`-d` từ chối xóa branch chưa được merge vào upstream hoặc HEAD phù hợp. `-D` bỏ qua kiểm tra đó và có thể làm mất công việc chưa được tích hợp; chỉ dùng khi đã xác minh branch không còn dữ liệu cần giữ.

## 6. Xóa branch trên remote và cập nhật Config Server

Xóa branch trên Git server thường được thực hiện sau khi pull request đã merge và nhóm xác nhận không còn client cần label đó.

Có thể xóa remote branch bằng Git CLI:

```bash
git push origin --delete feature/old-config
```

Hoặc dùng giao diện Git provider để xóa branch sau khi merge. Sau đó:

1. Xác nhận branch đã biến mất khỏi danh sách remote branches.
2. Chờ lần fetch tiếp theo của Config Server hoặc thực hiện quy trình refresh/restart đã được phê duyệt.
3. Kiểm tra log để xác nhận server phát hiện ref bị xóa và local branch tương ứng được dọn khi `delete-untracked-branches` bật.
4. Gọi endpoint Config Server với label cũ để xác nhận server không còn trả cấu hình từ local branch stale.
5. Kiểm tra các client đang dùng label đó và chuyển chúng sang label được hỗ trợ.

Không xóa branch chỉ vì pull request đã merge nếu branch vẫn được một client dùng làm label hoặc làm nhánh dự phòng. Việc xóa remote branch và dọn local branch của Config Server cần nằm trong cùng quy trình quản trị thay đổi.

## 7. Tag cũ cần chính sách riêng

Tag và branch đều có thể được dùng làm label, nhưng `delete-untracked-branches` chỉ xử lý local branch có remote-tracking branch tương ứng đã bị xóa. Không nên kỳ vọng thuộc tính này dọn các tag cũ.

Tag thường được dùng để ghim cấu hình production hoặc đánh dấu release. Vì vậy, chính sách lưu giữ tag cần thận trọng hơn chính sách dọn branch tạm:

- Giữ tag của các bản phát hành còn đang được triển khai.
- Giữ tag trong khoảng thời gian rollback hoặc kiểm toán yêu cầu.
- Chỉ xóa tag sau khi xác nhận không còn client hoặc pipeline cần dùng.
- Bảo vệ tag release khỏi bị di chuyển hoặc ghi đè.
- Ghi lại commit SHA tương ứng để có thể truy vết nội dung đã phát hành.

Trong clone developer, `git fetch --prune` thông thường không tự xóa tag được fetch theo cơ chế auto-follow. `--prune-tags` có thể xóa local tags không còn trên remote nếu refspec phù hợp; tùy chọn này cần dùng cẩn thận vì local tag có thể được tạo từ nguồn khác hoặc được dùng cho mục đích riêng.

Nếu cần xóa một tag, phải xác nhận trước rằng không còn release nào tham chiếu đến nó. Ví dụ:

```bash
git tag -d config-v1.4.0
git push origin :refs/tags/config-v1.4.0
```

Lệnh đầu xóa tag trong clone hiện tại; lệnh sau xóa tag trên remote. Việc xóa tag remote không đồng nghĩa mọi clone hoặc cache của Config Server lập tức xóa tag local. Hãy kiểm tra hành vi của backend và quy trình lưu giữ tag theo phiên bản đang triển khai.

## 8. Phân biệt delete-untracked-branches với force-pull

Hai thuộc tính này giải quyết hai vấn đề khác nhau:

| Thuộc tính | Tác dụng | Không dùng để |
|---|---|---|
| `delete-untracked-branches` | Xóa local branch khi fetch phát hiện branch tương ứng đã bị xóa trên remote. | Xóa remote branch, xóa tag hoặc reset mọi thay đổi file local. |
| `force-pull` | Buộc working copy local quay về trạng thái remote khi phát hiện local copy bị dirty/diverged theo cơ chế của Config Server. | Thay thế chính sách prune branch hoặc xóa tag. |

`force-pull` có thể bỏ các thay đổi local trong working copy. Trong Config Server, working copy nên được xem là cache chỉ đọc, nhưng vẫn cần xác định nguyên nhân làm nó dirty trước khi bật chế độ force. Không bật `force-pull` chỉ để xử lý branch stale; hãy dùng đúng thuộc tính `delete-untracked-branches` cho mục đích đó.

## 9. Quy trình dọn branch an toàn

Một quy trình phù hợp cho repository cấu hình có thể gồm:

1. **Kiểm kê label đang dùng**: xác định application, profile, label và revision của các client đang triển khai.
2. **Kiểm tra người dùng branch**: xác nhận branch không còn được client, pipeline, môi trường staging hoặc quy trình rollback tham chiếu.
3. **Merge và review**: bảo đảm nội dung cần giữ đã được merge vào branch chính hoặc tag phát hành.
4. **Xóa remote branch**: dùng pull request hoặc quyền quản trị repository theo quy trình của nhóm.
5. **Đồng bộ Config Server**: bảo đảm server fetch remote và bật `delete-untracked-branches` nếu cần dọn local branch tự động.
6. **Xác minh**: gọi endpoint với label cũ và label mới; kiểm tra server không trả cấu hình cũ.
7. **Theo dõi client**: tìm client còn gửi label cũ qua log, metric hoặc thông tin triển khai; cập nhật chúng theo kế hoạch.
8. **Lưu dấu vết**: ghi lại branch đã xóa, commit cuối, thời điểm, người phê duyệt và label thay thế.

Trước khi dọn một branch dùng chung, hãy xác nhận tất cả dịch vụ đã chuyển sang label thay thế. Nếu một dịch vụ vẫn dùng branch cũ, request của nó có thể thất bại sau khi local branch bị dọn.

## 10. Cấu hình mẫu cho môi trường có nhiều branch tạm

Với remote Git repository, cấu hình có thể bật dọn local branch và chọn tần suất fetch phù hợp:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: ${CONFIG_REPO_URI}
          default-label: main
          basedir: ${CONFIG_GIT_BASEDIR:/var/cache/config-server}
          delete-untracked-branches: true
          refresh-rate: 0
```

Trong ví dụ này, Config Server fetch theo request và xóa local branch khi fetch xác nhận branch tương ứng đã bị xóa trên remote. Nếu repository ít thay đổi và có nhiều request, có thể chọn `refresh-rate` dương để giảm tần suất fetch; đổi lại, việc phát hiện branch bị xóa cũng có thể chậm hơn.

Với nhiều repository được định tuyến theo application pattern, hãy kiểm thử riêng từng repository. Cần xác nhận mỗi repository có credential, default label, refresh behavior và chính sách dọn branch phù hợp. Đừng giả định việc bật một thuộc tính ở cấu hình gốc sẽ tạo ra cùng hành vi cho mọi override theo repository nếu phiên bản hoặc cấu hình của dự án có cách bind riêng.

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Branch đã xóa trên remote nhưng Config Server vẫn trả cấu hình | Local branch trong working copy vẫn tồn tại; `delete-untracked-branches` đang tắt hoặc server chưa fetch. | Bật thuộc tính, kiểm tra `refresh-rate` và xác minh fetch đã phát hiện ref deletion. |
| Client dùng danh sách label dự phòng nhưng vẫn nhận branch cũ | Label đầu tiên còn tồn tại dưới dạng local branch stale nên server không chuyển sang label sau. | Dọn local branch, sau đó kiểm tra lại request với toàn bộ danh sách label. |
| `delete-untracked-branches` đã bật nhưng branch vẫn còn | Chưa có lần fetch mới, refresh bị tắt hoặc Git backend không truy cập được remote. | Kiểm tra refresh rate, log fetch, mạng và quyền Git. |
| Branch local trong máy developer vẫn hiện sau khi remote đã xóa | Clone developer chưa prune remote-tracking refs hoặc local branch riêng vẫn còn. | Chạy `git fetch --prune origin`, rồi kiểm tra và xóa local branch đã merge. |
| Tag cũ vẫn có thể được dùng làm label | Thuộc tính chỉ dọn local branches, không dọn tags. | Áp dụng chính sách lưu giữ/xóa tag riêng và xác minh client không còn tham chiếu. |
| Cấu hình bị thay đổi sau khi bật `force-pull` | Working copy có local modification bị reset về remote. | Chỉ bật force-pull khi hiểu rõ tác động và xử lý nguyên nhân làm cache dirty. |
| Client không lấy được cấu hình sau khi dọn branch | Client vẫn yêu cầu label đã bị xóa và không có label dự phòng hợp lệ. | Cập nhật client sang branch/tag còn tồn tại và triển khai lại theo kế hoạch. |

Khi điều tra, hãy xác định branch có còn trên remote không, Config Server đã fetch lần cuối khi nào, local branch còn tồn tại không, client đang gửi label nào và tag/revision thay thế có hợp lệ không.

## 12. Bài thực hành

### Bước 1: Tạo branch thử nghiệm

Tạo branch `feature/temporary-config` trong repository cấu hình, thêm một giá trị dễ nhận biết và yêu cầu Config Server trả cấu hình theo label này.

**Kết quả cần đạt:** xác nhận Config Server đã fetch và checkout branch thành local branch trong working copy.

### Bước 2: Xóa branch trên remote

Merge nội dung cần giữ, sau đó xóa `feature/temporary-config` khỏi remote. Chưa bật `delete-untracked-branches` và gọi lại endpoint bằng label cũ.

**Kết quả cần đạt:** quan sát được nguy cơ local branch cũ vẫn có thể được phục vụ sau khi remote branch đã bị xóa.

### Bước 3: Bật dọn local branch

Cấu hình `spring.cloud.config.server.git.delete-untracked-branches: true`, bảo đảm Config Server thực hiện fetch và gọi lại endpoint.

**Kết quả cần đạt:** xác nhận local branch tương ứng được dọn và label đã xóa không còn được phục vụ từ cache cũ.

### Bước 4: Kiểm tra refresh rate

Thử `refresh-rate: 0`, một giá trị dương và giá trị âm trong môi trường thử nghiệm. Quan sát thời điểm Config Server phát hiện branch bị xóa.

**Kết quả cần đạt:** giải thích được vì sao thuộc tính dọn branch phụ thuộc vào lần fetch.

### Bước 5: Phân biệt branch và tag

Tạo tag release và dùng tag làm label. Xóa một branch khác, bật `delete-untracked-branches` rồi kiểm tra tag vẫn tồn tại. Xây dựng chính sách lưu giữ tag riêng.

**Kết quả cần đạt:** không nhầm dọn local branch với xóa tag hoặc xóa Git object.

## 13. Tự kiểm tra

1. Vì sao xóa remote branch chưa chắc làm Config Server ngừng phục vụ branch đó ngay lập tức?
2. Remote branch, remote-tracking ref và local branch khác nhau thế nào?
3. `spring.cloud.config.server.git.delete-untracked-branches` thực hiện thao tác gì và mặc định là bao nhiêu?
4. Vì sao `delete-untracked-branches` chỉ có tác dụng sau khi Config Server fetch remote?
5. `refresh-rate` bằng 0, dương và âm ảnh hưởng thế nào đến việc phát hiện branch bị xóa?
6. Vì sao `git fetch --prune` trên máy developer không trực tiếp dọn cache của Config Server?
7. Vì sao tag cần chính sách lưu giữ riêng?
8. `force-pull` khác gì với `delete-untracked-branches`?
9. Cần xác nhận điều gì trước khi xóa branch cấu hình đang được dùng làm label?

## Tài liệu tham khảo

- [Spring Cloud Config – Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html): `deleteUntrackedBranches`, `refreshRate`, `force-pull` và hành vi Git backend.
- [Git – git-fetch](https://git-scm.com/docs/git-fetch): cập nhật refs và quy tắc prune remote-tracking refs/tags.
- [Git – git-remote](https://git-scm.com/docs/git-remote): lệnh `git remote prune` và cách quản lý remote.
