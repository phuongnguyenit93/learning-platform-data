# Force push, --force-with-lease và giới hạn bảo vệ khi có fetch nền

Khi viết lại lịch sử của một nhánh đã được đẩy lên remote, chẳng hạn sau khi rebase hoặc squash commit, Git thường từ chối push vì cập nhật mới không còn là fast-forward. `git push --force` có thể ghi đè đầu nhánh remote để thay bằng lịch sử local, nhưng cũng có thể làm mất commit mà người khác vừa đẩy lên.

`git push --force-with-lease` bổ sung một điều kiện: chỉ cho phép cập nhật khi ref remote vẫn có giá trị mà phía local đang kỳ vọng. Đây là một lớp bảo vệ hữu ích khi cộng tác, nhưng mức bảo vệ phụ thuộc vào cách Git lấy giá trị kỳ vọng. Một tiến trình fetch chạy nền có thể cập nhật remote-tracking branch và làm dạng lease mặc định mất khả năng phát hiện một commit mà bạn chưa xem xét.

## 1. Vì sao cần force push?

Một lần push thông thường yêu cầu cập nhật remote theo hướng fast-forward: lịch sử mới phải chứa lịch sử hiện tại của nhánh remote. Điều này ngăn một lần push vô tình làm biến mất các commit đã có trên remote.

Ví dụ, nhánh local và remote ban đầu cùng ở đầu nhánh `C`, với lịch sử `A-B-C`:

```text
A---B---C  (origin/feature, feature)
```

Bạn sửa lịch sử local bằng rebase hoặc squash, tạo ra một chuỗi commit mới:

```text
A---B---C       (origin/feature)
 \
  D'---E'       (feature)
```

Trong sơ đồ, `D'` và `E'` là các commit mới thay thế lịch sử `B` và `C`. Nhánh local không còn là hậu duệ của đầu nhánh remote, nên push thông thường bị từ chối với lỗi non-fast-forward.

Force push yêu cầu remote chuyển ref sang commit mới dù lịch sử cũ không phải tổ tiên của lịch sử mới:

```bash
git push --force origin feature
```

Lệnh này có thể ghi đè các commit remote mà local chưa biết hoặc chưa đưa vào lịch sử mới. Nếu một đồng đội vừa đẩy commit `F` lên remote sau lần fetch cuối của bạn, force push có thể làm `F` biến mất khỏi đầu nhánh được chia sẻ.

Force push chỉ thay đổi ref trên remote; nó không tự hợp nhất các commit bị ghi đè và không bảo đảm những người khác đã cập nhật bản sao local. Vì vậy, hãy xác định rõ nhánh đích và phạm vi refspec trước khi dùng.

## 2. `--force` và `--force-with-lease` khác nhau thế nào?

`--force` bỏ qua kiểm tra fast-forward cho ref được push. Nó không kiểm tra xem đầu nhánh remote có thay đổi kể từ lần bạn quan sát hay không.

`--force-with-lease` yêu cầu giá trị hiện tại của ref remote phải khớp với giá trị kỳ vọng. Nếu remote đã thay đổi, Git từ chối push để bạn có cơ hội fetch, xem thay đổi mới và tích hợp chúng.

| Lệnh | Điều kiện cho phép cập nhật | Mức bảo vệ |
|---|---|---|
| `git push --force` | Không yêu cầu fast-forward | Có thể ghi đè thay đổi remote chưa được xem xét |
| `git push --force-with-lease` | Ref remote phải khớp giá trị kỳ vọng từ remote-tracking ref | Phát hiện thay đổi remote nếu giá trị kỳ vọng chưa bị cập nhật |
| `git push --force-with-lease=<ref>:<expect>` | Ref remote phải đúng bằng OID được chỉ định | So sánh với một giá trị kỳ vọng cố định |
| `git push --force-with-lease --force-if-includes` | Lease mặc định kèm kiểm tra bổ sung về việc tích hợp đầu remote-tracking | Hữu ích khi có fetch nền cập nhật remote-tracking ref |

Trong cấu hình thông thường, khi chạy:

```bash
git push --force-with-lease origin HEAD:refs/heads/feature
```

Git lấy giá trị kỳ vọng từ remote-tracking branch tương ứng, thường là `refs/remotes/origin/feature`. Nếu ref remote không còn bằng giá trị đó, push bị từ chối.

Lease là một phép kiểm tra giá trị ref tại thời điểm cập nhật. Nó không tự đọc hiểu nội dung commit, không hợp nhất thay đổi và không thay thế việc xem xét lịch sử.

## 3. Tình huống fetch nền làm suy yếu lease mặc định

Giả sử nhánh local và remote ban đầu cùng ở đầu nhánh `C`, với lịch sử `A-B-C`. Bạn viết lại hai commit `B` và `C` thành `D'` và `E'` trên nền `A`. Trong lúc bạn làm việc, IDE hoặc một tiến trình tự động chạy `git fetch origin`.

Trước khi fetch nền:

```text
A---B---C  (origin/feature)
 \
  D'---E'  (feature)

```

Một đồng đội đẩy commit `F` lên remote. Fetch nền nhận commit đó và cập nhật remote-tracking ref:

```text
A---B---C---F  (origin/feature)
 \
  D'---E'  (feature)
```

Nhánh local của bạn vẫn dựa trên `A`; bạn chưa xem xét hoặc tích hợp `F`. Nhưng remote-tracking ref `origin/feature` đã được tiến trình nền cập nhật thành `F`.

Nếu bạn dùng dạng lease mặc định, Git có thể lấy `F` làm giá trị kỳ vọng. Remote cũng đang ở `F`, nên phép so sánh lease thành công. Git không biết rằng lịch sử local của bạn vẫn bỏ qua commit `F`, và có thể cho phép force push thay đầu nhánh remote bằng `E'`.

Đó là giới hạn quan trọng: **lease mặc định dựa trên remote-tracking ref hiện tại, không phải một bản ghi bất biến về commit remote mà bạn đã xem xét trước khi viết lại lịch sử**. Nếu fetch nền cập nhật ref này, giá trị kỳ vọng cũng thay đổi theo.

Fetch nền thường đến từ IDE, GUI Git client, extension, script đồng bộ hoặc một terminal khác. Bạn có thể không nhận ra nó đã chạy.

## 4. Dùng expected OID cố định

Để tránh việc remote-tracking ref bị thay đổi làm trôi giá trị kỳ vọng, có thể chỉ định rõ OID mà remote ref phải có:

```bash
git push --force-with-lease=refs/heads/feature:EXPECTED_OID origin HEAD:refs/heads/feature
```

Thay `EXPECTED_OID` bằng mã commit đầy đủ đã ghi nhận tại thời điểm bạn xác định nhánh remote mà công việc của mình dựa trên đó.

Git chỉ cho phép cập nhật nếu `refs/heads/feature` trên remote vẫn đúng bằng OID đã chỉ định. Nếu đồng đội đẩy thêm commit sau thời điểm đó, remote ref đổi sang OID khác và push bị từ chối, kể cả khi fetch nền đã cập nhật `origin/feature` trên máy bạn.

Một quy trình sử dụng expected OID cố định:

1. Fetch remote tại một thời điểm có chủ đích và kiểm tra lịch sử nhánh.
2. Ghi lại OID của đầu nhánh remote mà bạn đã xem xét, trước khi viết lại lịch sử local.
3. Tạo hoặc rebase các commit local dựa trên lịch sử đã kiểm tra.
4. Push với `--force-with-lease=refs/heads/<branch>:<expected-oid>`.
5. Nếu bị từ chối, fetch và xem commit mới; tích hợp thay đổi cần giữ, sau đó xác định lại OID kỳ vọng trước khi thử lại.

Có thể lấy OID của remote-tracking ref bằng:

```bash
git rev-parse refs/remotes/origin/feature
```

Hãy ghi lại kết quả ở thời điểm phù hợp và giữ nguyên nó trong lúc làm việc. Nếu bạn chỉ chạy lệnh trên sau khi fetch nền đã cập nhật ref, OID mới có thể đại diện cho commit bạn chưa xem xét; việc chỉ định rõ OID không tự làm cho giá trị đó trở nên an toàn.

Thay vì chép OID ra ghi chú, bạn có thể ghim nó vào một tag local trước khi viết lại lịch sử:

```bash
git fetch origin
git log --oneline --decorate -10 refs/remotes/origin/feature
git tag feature-base refs/remotes/origin/feature

# Sau khi đã kiểm tra và viết lại lịch sử local
git push --force-with-lease=refs/heads/feature:feature-base origin HEAD:refs/heads/feature
```

Tag `feature-base` giữ nguyên OID đã ghi nhận ngay cả khi fetch nền cập nhật `origin/feature`. Chọn một tên tag chưa tồn tại và không di chuyển tag đó trong lúc làm việc; sau khi push xong có thể xóa tag local bằng `git tag -d feature-base` nếu không cần dùng lại.

Một cách khác để quan sát OID trực tiếp trên remote là:

```bash
git ls-remote origin refs/heads/feature
```

Lệnh này hiển thị OID hiện tại của ref trên remote tại thời điểm truy vấn. Nó hữu ích để kiểm tra trạng thái remote, nhưng không thay thế việc xem xét commit. Nếu bạn lấy OID sau khi người khác đã đẩy một commit mà bạn chưa tích hợp rồi dùng ngay làm expected value, lease vẫn có thể cho phép ghi đè commit đó. Hãy đối chiếu lịch sử và chỉ dùng giá trị kỳ vọng gắn với trạng thái mà bạn thực sự đã kiểm tra.

## 5. Kết hợp `--force-if-includes`

Git cung cấp `--force-if-includes` như một lớp kiểm tra bổ sung khi dùng cùng `--force-with-lease` ở dạng không chỉ định expected OID. Tùy chọn này kiểm tra xem đầu remote-tracking ref có thể đi tới từ một trong các entry reflog của nhánh local được tạo dựa trên ref đó để viết lại lịch sử hay không. Mục đích là giúp phát hiện tình huống remote-tracking ref được fetch nền cập nhật nhưng nhánh local chưa tích hợp thay đổi đó.

Ví dụ:

```bash
git push --force-with-lease --force-if-includes origin HEAD:refs/heads/feature
```

Đây là một safeguard hữu ích khi công cụ khác có thể chạy fetch nền. `--force-if-includes` không thay thế lease và không phải là cách tự động hợp nhất commit. Nếu kiểm tra không đạt, push bị từ chối để bạn kiểm tra lịch sử.

Cần nhớ:

- `--force-if-includes` được thiết kế để bổ sung cho dạng `--force-with-lease` dựa trên remote-tracking ref, đặc biệt khi có fetch nền.
- Dùng riêng `--force-if-includes` mà không có `--force-with-lease` không tạo ra bảo vệ force-push tương đương.
- Khi dùng cùng `--force-with-lease=<ref>:<expect>` có expected OID tường minh, `--force-if-includes` là no-op; lease tường minh đã so sánh với giá trị cố định.
- Nó không xác minh thay cho bạn rằng mọi thay đổi đều đúng về mặt nghiệp vụ hoặc test.
- Khi cần một mốc kỳ vọng cố định và rõ ràng, dùng `--force-with-lease=<ref>:<expect>` với OID đã ghi nhận.

## 6. Cách ly remote-tracking ref dùng cho push

Một chiến lược khác là tạo remote riêng dành cho push, để các lần fetch nền từ remote làm việc chính không cập nhật ref dùng làm giá trị kỳ vọng.

Ví dụ, thêm một remote trỏ tới cùng URL:

```bash
git remote add origin-push REMOTE_URL
git fetch origin-push
```

Thay `REMOTE_URL` bằng URL của repository remote mà bạn định push tới; hãy xác nhận đó là đúng repository trước khi thêm remote.

Remote `origin-push` có bộ remote-tracking ref riêng, chẳng hạn `refs/remotes/origin-push/feature`. Nếu IDE chỉ tự động fetch `origin`, ref dưới `origin-push` không bị lần fetch đó cập nhật.

Sau khi đã kiểm tra và ghi nhận trạng thái từ remote push, có thể dùng:

```bash
git push --force-with-lease origin-push HEAD:refs/heads/feature
```

Cách này giúp lease mặc định tham chiếu đến một remote-tracking ref ít bị tiến trình nền tác động. Bạn vẫn phải chủ động fetch `origin-push` và kiểm tra thay đổi trước khi viết lại lịch sử hoặc push. Nếu fetch remote riêng sau khi một commit mới đã xuất hiện nhưng chưa được tích hợp, lease lại có thể chấp nhận giá trị mới đó.

Kiểm tra cấu hình remote:

```bash
git remote -v
git config --get-all remote.origin.push
git config --get-all remote.origin-push.fetch
```

Chỉ thêm remote riêng khi bạn hiểu URL và refspec đang dùng. Không nên vô tình trỏ remote push sang một repository khác hoặc một fork không phải đích dự định.

## 7. Quy trình force push có kiểm soát

Một quy trình thực tế khi cần đẩy lịch sử đã rebase lên nhánh chia sẻ:

```bash
# 1. Kiểm tra nhánh và trạng thái local
git status
git branch --show-current

# 2. Fetch và xem trạng thái remote tại một thời điểm có chủ đích
git fetch origin
git log --oneline --graph --decorate --all -20

# 3. Kiểm tra OID đầu nhánh remote và ghi lại giá trị đã xem xét
git rev-parse refs/remotes/origin/feature

# 4. Xem những commit local khác với remote
git log --oneline origin/feature..HEAD
git log --oneline HEAD..origin/feature

# 5. Sau khi rebase/squash và kiểm tra kết quả,
#    push với expected OID đã ghi lại ở bước 3
git push --force-with-lease=refs/heads/feature:EXPECTED_OID origin HEAD:refs/heads/feature
```

Trong quy trình này, lệnh `git log origin/feature..HEAD` hiển thị commit có ở local mà chưa có trong remote-tracking ref; chiều ngược lại cho thấy commit remote-tracking mà local chưa có. Hãy kiểm tra cả hai phía trước khi quyết định viết lại lịch sử.

Nếu push bị từ chối:

1. Không đổi sang `--force` chỉ để vượt qua lỗi.
2. Chạy `git fetch origin` và kiểm tra commit mới trên remote.
3. Xác định thay đổi nào cần giữ; có thể rebase lại, cherry-pick hoặc phối hợp với đồng đội.
4. Chạy test phù hợp.
5. Ghi nhận OID kỳ vọng mới sau khi đã kiểm tra và push lại bằng lease.

Nếu nhiều người đang làm việc trên cùng nhánh, hãy trao đổi trước khi viết lại lịch sử. Force push có thể khiến bản sao local của đồng đội trở nên phân kỳ; họ cần biết nhánh đã được viết lại và cách cập nhật an toàn.

## 8. Giới hạn của lease và bảo vệ phía server

`--force-with-lease` là kiểm tra ở phía client đối với giá trị ref remote. Nó không phải cơ chế khóa nhánh và không thể thay thế quy tắc bảo vệ ở máy chủ.

Một số giới hạn cần hiểu rõ:

- **Không xác minh nội dung đã được xem xét:** nếu bạn chỉ định sai hoặc chọn một expected OID mà bạn chưa kiểm tra, lease vẫn có thể chấp nhận khi remote ref đúng bằng OID đó.
- **Không ngăn được chính bạn ghi đè lịch sử đã biết:** nếu remote vẫn ở đúng expected OID, Git cho phép cập nhật ngay cả khi kết quả mới loại bỏ commit ở OID đó. Đó là mục đích của force push; trách nhiệm chọn lịch sử đúng thuộc về người thực hiện.
- **Không chống mọi lỗi refspec:** nếu push nhầm tên remote hoặc nhánh đích, một lease hợp lệ cho ref đó vẫn có thể cập nhật nhầm nơi. `--force` cũng áp dụng cho tất cả ref đang được push; hãy dùng refspec tường minh như `HEAD:refs/heads/feature` để giới hạn đúng nhánh cần cập nhật.
- **Không bỏ qua chính sách server:** branch protection, quyền người dùng, hook phía nhận hoặc cấu hình cấm non-fast-forward có thể từ chối push. Client không thể dùng `--force` để vượt qua các chính sách này.
- **Không thay thế phối hợp nhóm:** các cộng tác viên có thể đang dựa trên lịch sử cũ; cần thông báo và hướng dẫn họ đồng bộ sau khi nhánh được viết lại.

Các dạng `--force-with-lease` không chỉ định expected OID tường minh hiện được tài liệu Git đánh dấu là experimental; nếu cần hành vi so sánh cố định, hãy dùng dạng `<ref>:<expect>`. Để kiểm tra nhánh có chính sách bảo vệ, xem quy định của nền tảng lưu trữ mã nguồn hoặc hỏi người quản trị repository. Nếu server cấm force push, hãy dùng quy trình pull request hoặc nhánh thay thế được tổ chức cho phép.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| `--force-with-lease` luôn an toàn tuyệt đối | Lease mặc định có thể bị ảnh hưởng khi fetch nền cập nhật remote-tracking ref |
| Fetch nền chỉ cập nhật dữ liệu, không ảnh hưởng push | Nó có thể thay đổi giá trị kỳ vọng mà lease mặc định sử dụng |
| Chỉ cần fetch ngay trước khi push là đủ | Fetch có thể cho biết remote mới, nhưng nếu chưa xem xét commit mới thì lease vẫn có thể cho phép ghi đè |
| `--force-if-includes` thay thế lease | Đây là kiểm tra bổ sung dùng cùng lease, không phải tùy chọn thay thế |
| Lease sẽ tự hợp nhất commit mới | Lease chỉ cho phép hoặc từ chối cập nhật ref; nó không tích hợp commit |
| Server cho phép force push nếu client dùng `--force` | Quy tắc branch protection, hook và quyền phía server vẫn có hiệu lực |

## Kết luận

Dùng `--force` có thể ghi đè đầu nhánh remote mà không kiểm tra thay đổi mới. `--force-with-lease` thêm điều kiện so sánh giá trị ref, nhưng dạng mặc định dựa vào remote-tracking ref có thể mất tác dụng bảo vệ khi fetch nền cập nhật ref đó. Với lịch sử quan trọng, hãy ghi nhận một expected OID đã kiểm tra trước khi viết lại lịch sử và dùng dạng lease chỉ định OID; có thể kết hợp `--force-if-includes` hoặc dùng remote push riêng để giảm rủi ro từ fetch nền. Luôn kiểm tra refspec, xem lịch sử hai phía, và tuân thủ chính sách bảo vệ nhánh của server.
