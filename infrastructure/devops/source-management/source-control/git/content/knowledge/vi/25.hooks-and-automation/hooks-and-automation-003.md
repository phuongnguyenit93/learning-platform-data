# Các thời điểm pre-push, pre-receive, update và post-receive

Git hooks là các chương trình được Git gọi tại những thời điểm xác định trong một thao tác. Với quy trình push, bốn hook quan trọng là **pre-push**, **pre-receive**, **update** và **post-receive**. Tên của chúng khá giống nhau nhưng chạy ở những nơi khác nhau, nhận dữ liệu khác nhau và có quyền quyết định khác nhau đối với lần push.

Trong chương **Hook và tự động hóa** của module **SOURCE_CONTROL_GIT**, bài học này tập trung vào vòng đời của một lần push. Bạn sẽ phân biệt hook phía máy người đẩy với hook phía repository nhận, biết hook nào có thể từ chối toàn bộ lần push, hook nào chỉ từ chối một ref, và hook nào chỉ chạy sau khi ref đã được cập nhật. Đây là nền tảng để đặt kiểm tra chất lượng, chính sách bảo vệ branch, ghi nhận sự kiện và kích hoạt triển khai ở đúng thời điểm.

Sau bài học, bạn có thể:

- Mô tả thứ tự chạy của pre-push, pre-receive, update và post-receive.
- Phân biệt hook client-side với hook server-side.
- Đọc tham số và dữ liệu stdin mà từng hook nhận.
- Chọn đúng hook cho kiểm thử trước push, kiểm tra chính sách, bảo vệ từng ref hoặc thông báo sau push.
- Giải thích phạm vi từ chối của pre-receive và update.
- Hiểu vì sao post-receive không thể hủy một lần push đã được chấp nhận.
- Cấu hình vị trí hooks, kiểm tra quyền thực thi và xử lý lỗi hook.

## 1. Git hook là gì?

Hook là một chương trình mà Git tìm và chạy khi một sự kiện nhất định xảy ra. Hook thường là shell script, nhưng có thể là chương trình hoặc script dùng ngôn ngữ khác, miễn môi trường chạy có thể thực thi nó.

Ví dụ:

- pre-push chạy ở repository phía client trước khi Git gửi cập nhật lên remote.
- pre-receive chạy ở repository phía server khi nhận một lần push, trước khi cập nhật các ref.
- update chạy ở server riêng cho từng ref đang được cập nhật.
- post-receive chạy ở server sau khi các ref được cập nhật thành công.

Hook không phải một commit hay một phần của lịch sử Git. Nó là chương trình nằm trong cấu hình môi trường của repository hoặc được chỉ định qua hooks path. Hook có thể kiểm tra dữ liệu, từ chối thao tác, ghi log, gửi thông báo hoặc khởi chạy công việc khác.

Điều quan trọng là chọn hook theo thời điểm cần can thiệp. Một kiểm tra cần ngăn push không hợp lệ phải chạy trước khi ref được cập nhật. Một tác vụ triển khai cần commit mới đã tồn tại trên server phải chạy sau khi cập nhật thành công.

## 2. Vòng đời một lần push

Khi người dùng chạy git push, Git có thể đi qua các bước chính sau:

~~~text
Máy người đẩy (client)                  Repository nhận (server)

git push
   |
   v
pre-push
   |  non-zero -> dừng push
   |
   v
Kết nối và gửi dữ liệu ----------------> receive-pack nhận cập nhật
                                           |
                                           v
                                      pre-receive
                                           | non-zero
                                           | -> từ chối toàn bộ
                                           v
                                      update (mỗi ref)
                                           | non-zero
                                           | -> từ chối ref đó
                                           v
                                      Cập nhật các ref được chấp nhận
                                           |
                                           v
                                      post-receive
                                           |
                                           v
                                      Thông báo / triển khai
~~~

Sơ đồ mô tả luồng phổ biến. Nếu pre-push từ chối, client không tiếp tục push. Nếu pre-receive từ chối, server không chấp nhận các ref trong lần nhận đó. Nếu update từ chối một ref, những ref khác vẫn có thể được cập nhật nếu hợp lệ. Post-receive chỉ xử lý các ref đã được cập nhật thành công.

Không phải mọi lần push đều cập nhật ref. Ví dụ push không có thay đổi hoặc bị từ chối sớm có thể không đi đến các bước sau. Vì vậy, hãy thiết kế hook dựa trên sự kiện thực tế mà nó được gọi.

## 3. Bảng so sánh bốn hook

| Hook | Chạy ở đâu? | Thời điểm | Dữ liệu chính | Có thể từ chối? |
| --- | --- | --- | --- | --- |
| pre-push | Client | Trước khi push cập nhật remote | Tên remote, URL và danh sách ref định push | Có, dừng lần push từ client |
| pre-receive | Server | Khi nhận push, trước cập nhật ref | Danh sách old OID, new OID, ref name qua stdin | Có, từ chối toàn bộ lần nhận |
| update | Server | Riêng từng ref, trước khi cập nhật ref đó | ref name, old OID, new OID qua đối số | Có, từ chối riêng ref đó |
| post-receive | Server | Sau khi cập nhật ref thành công | Danh sách ref đã cập nhật qua stdin | Không thể từ chối hoặc hoàn tác push đã thành công |

OID là object ID, thường được gọi là commit hash trong trường hợp ref trỏ đến commit. Git cũng có thể dùng object format SHA-256, vì vậy không nên giả định mọi hash luôn có 40 ký tự.

## 4. pre-push: kiểm tra ở máy người đẩy

pre-push là client-side hook. Git gọi hook này trong repository đang thực hiện lệnh push, trước khi các cập nhật được gửi để thay đổi ref trên remote.

Hook nhận hai đối số:

1. Tên remote, ví dụ origin.
2. Địa chỉ remote mà Git sẽ push tới.

Ngoài ra, Git gửi danh sách ref dự định cập nhật qua stdin. Mỗi dòng có bốn trường:

~~~text
<local-ref> <local-oid> <remote-ref> <remote-oid>
~~~

Trong đó:

- local-ref là ref phía local được dùng làm nguồn.
- local-oid là object ID phía local.
- remote-ref là ref phía remote sẽ được cập nhật.
- remote-oid là object ID hiện tại phía remote.

Khi tạo một ref mới trên remote, remote-oid là chuỗi số 0. Khi xóa ref remote, local-ref có thể là (delete) và local-oid là chuỗi số 0. Độ dài chuỗi số 0 phụ thuộc object format của repository.

### Khi nào dùng pre-push?

- Chạy unit test hoặc kiểm tra định dạng trước khi gửi code.
- Kiểm tra commit sắp push có chứa file không được phép.
- Nhắc người dùng cập nhật tài liệu hoặc kiểm tra migration.
- Chặn push từ máy cá nhân nếu branch chưa đạt một điều kiện nội bộ.

Ví dụ hook chạy test trước mỗi lần push:

~~~sh
#!/bin/sh
set -eu

echo "Running checks before push to $1 ($2)" >&2
./scripts/test.sh
~~~

Đặt file với tên pre-push trong hooks directory đang áp dụng và cấp quyền thực thi trên hệ thống Unix-like. Nếu script trả mã khác 0, Git dừng lần push. Script trên minh họa việc chạy test; hook thực tế có thể đọc stdin để chỉ kiểm tra các ref hoặc commit liên quan.

### pre-push không phải chính sách bảo mật của server

Hook nằm trên máy người dùng nên người dùng có thể không cài, sửa hoặc bỏ qua nó. Tùy chọn git push --no-verify bỏ qua pre-push. Vì vậy, pre-push phù hợp với phản hồi nhanh và kiểm tra hỗ trợ người phát triển. Quy tắc bắt buộc của tổ chức phải được thực thi ở server hoặc nền tảng quản lý repository.

## 5. pre-receive: kiểm tra toàn bộ lần push ở server

pre-receive là server-side hook. Git gọi hook một lần cho mỗi lần nhận push, trước khi cập nhật các ref. Hook nhận qua stdin một dòng cho mỗi ref được đề xuất:

~~~text
<old-oid> <new-oid> <ref-name>
~~~

Trong đó:

- old-oid là object ID hiện tại của ref trên server.
- new-oid là object ID mới mà client muốn cập nhật.
- ref-name là tên đầy đủ, ví dụ refs/heads/main hoặc refs/tags/v1.2.0.

Nếu tạo ref mới, old-oid là chuỗi số 0. Nếu xóa ref, new-oid là chuỗi số 0.

pre-receive phù hợp với chính sách cần xem toàn bộ tập ref được push cùng lúc:

- Chặn cập nhật branch được bảo vệ nếu không đạt điều kiện.
- Kiểm tra commit hoặc metadata trên tất cả ref trước khi nhận.
- Ngăn xóa một branch quan trọng.
- Đảm bảo một nhóm tag hoặc branch được cập nhật theo quy tắc phát hành.

Nếu pre-receive trả mã khác 0, server từ chối toàn bộ lần push đó. Đây là lựa chọn phù hợp khi các ref trong cùng một lần push cần được chấp nhận hoặc từ chối như một nhóm.

### Ví dụ: không cho xóa main và không cho viết lại lịch sử main

~~~sh
#!/bin/sh

while read old new ref
do
    case "$ref" in
        refs/heads/main)
            case "$new" in
                *[!0]*)
                    ;;
                *)
                    echo "Deletion of main is not allowed" >&2
                    exit 1
                    ;;
            esac

            case "$old" in
                *[!0]*)
                    if ! git merge-base --is-ancestor "$old" "$new"
                    then
                        echo "Non-fast-forward update of main is not allowed" >&2
                        exit 1
                    fi
                    ;;
                *)
                    ;;
            esac
            ;;
    esac
done

exit 0
~~~

Ví dụ này dùng mẫu shell để nhận diện OID toàn số 0 mà không cố định độ dài hash. Với main đã tồn tại, hook yêu cầu old commit là tổ tiên của new commit; nếu không, cập nhật bị từ chối. Quy tắc này là ví dụ minh họa, nhóm vẫn cần cân nhắc quy trình merge và chính sách branch thực tế.

Trong hook server, hãy gửi thông báo từ chối qua stderr để người đẩy có thể đọc được lý do. Giữ kiểm tra đủ nhanh vì hook chạy đồng bộ trong quá trình push.

## 6. update: kiểm tra riêng từng ref

update cũng là server-side hook, nhưng khác pre-receive ở phạm vi gọi. Git gọi update một lần cho mỗi ref đang được cập nhật.

Hook nhận ba đối số:

~~~text
<ref-name> <old-oid> <new-oid>
~~~

Ví dụ:

- refs/heads/main
- OID cũ của main
- OID mới được đề xuất

update thích hợp khi chính sách có thể quyết định độc lập cho từng ref, chẳng hạn:

- Chỉ cho phép cập nhật một số namespace.
- Bảo vệ branch release.
- Từ chối xóa một ref cụ thể.
- Áp dụng quy tắc khác nhau cho branch và tag.

Nếu update trả mã khác 0, ref tương ứng bị từ chối. Những ref khác trong cùng lần push vẫn có thể được cập nhật. Đây là khác biệt quan trọng so với pre-receive, nơi một lần từ chối sẽ làm toàn bộ lần nhận bị từ chối.

### Ví dụ: bảo vệ branch release khỏi bị xóa

~~~sh
#!/bin/sh

ref_name=$1
old_oid=$2
new_oid=$3

case "$ref_name" in
    refs/heads/release/*)
        case "$new_oid" in
            *[!0]*)
                ;;
            *)
                echo "Release branches cannot be deleted" >&2
                exit 1
                ;;
        esac
        ;;
esac

exit 0
~~~

Hook này chỉ từ chối việc xóa các branch nằm trong refs/heads/release/. Những ref khác không bị ảnh hưởng bởi quy tắc này. Có thể mở rộng để kiểm tra fast-forward hoặc điều kiện khác cho từng ref.

### Khi nào chọn update thay vì pre-receive?

Chọn update khi quyết định chấp nhận có thể độc lập theo từng ref. Chọn pre-receive khi cần kiểm tra tất cả ref và từ chối cả lần push nếu bất kỳ ref nào vi phạm chính sách. Nếu dùng update cho một quy tắc phải giữ tính nhất quán giữa nhiều ref, hãy cẩn thận với khả năng push chỉ thành công một phần.

## 7. post-receive: xử lý sau khi ref đã cập nhật

post-receive là server-side hook chạy sau khi các ref được chấp nhận đã được cập nhật. Git gọi hook một lần cho lần nhận và truyền danh sách các ref cập nhật thành công qua stdin, theo định dạng:

~~~text
<old-oid> <new-oid> <ref-name>
~~~

Hook này phù hợp với các công việc cần commit mới đã có trong repository nhận:

- Gửi thông báo đến chat, email hoặc hệ thống theo dõi.
- Cập nhật dashboard hoặc audit log.
- Kích hoạt pipeline build và deploy.
- Đồng bộ metadata phát hành.
- Gửi sự kiện đến hệ thống tích hợp.

### post-receive không thể từ chối push đã hoàn tất

Đến thời điểm post-receive, các ref đã được cập nhật. Mã thoát khác 0 của hook không làm Git hoàn tác các ref và không biến lần push đã thành công thành bị từ chối.

Ví dụ, nếu hook triển khai ứng dụng thất bại:

- Commit vẫn đã được push vào branch.
- Ref trên server vẫn trỏ đến commit mới.
- Triển khai cần được retry hoặc xử lý qua hệ thống vận hành.

Vì vậy, không đặt kiểm tra bắt buộc trước khi nhận ở post-receive. Hãy đặt kiểm tra từ chối ở pre-receive hoặc update; dùng post-receive để thông báo và kích hoạt công việc sau khi dữ liệu đã được chấp nhận.

### Ví dụ: kích hoạt deploy khi main được cập nhật

~~~sh
#!/bin/sh

while read old new ref
do
    case "$ref" in
        refs/heads/main)
            if ! ./scripts/enqueue-deploy.sh "$new"
            then
                echo "Could not enqueue deployment for $new" >&2
            fi
            ;;
    esac
done

exit 0
~~~

Ví dụ gọi một script đưa yêu cầu triển khai vào hàng đợi. Thực tế nên thiết kế tác vụ có thể chạy lại, ghi log và không triển khai trùng ngoài ý muốn. Với công việc lâu, hãy enqueue job rồi kết thúc hook nhanh thay vì giữ kết nối push mở trong lúc build hoặc deploy kéo dài.

## 8. Chọn hook theo mục tiêu

| Mục tiêu | Hook phù hợp | Lý do |
| --- | --- | --- |
| Chạy test trước khi gửi code từ máy cá nhân | pre-push | Chạy trước khi client gửi cập nhật |
| Kiểm tra chính sách cho toàn bộ ref trong một lần push | pre-receive | Có danh sách tất cả ref và có thể từ chối toàn bộ |
| Áp dụng quy tắc độc lập cho từng branch hoặc tag | update | Được gọi riêng cho từng ref |
| Gửi thông báo sau khi branch đã được cập nhật | post-receive | Chỉ chạy sau khi ref được chấp nhận |
| Kích hoạt deploy từ commit mới trên main | post-receive | Commit mới đã có trong repository nhận |
| Bảo vệ branch khỏi force update | pre-receive hoặc update | Có thể kiểm tra quan hệ giữa OID cũ và mới trước cập nhật |

Một workflow có thể dùng nhiều hook. Ví dụ pre-push chạy test nhanh trên máy phát triển; pre-receive áp dụng chính sách bắt buộc ở server; post-receive gửi sự kiện cho CI. Mỗi hook nên có một trách nhiệm rõ ràng và tránh lặp cùng một kiểm tra tốn thời gian ở nhiều nơi.

## 9. Cài đặt hook ở đâu?

### Hooks directory mặc định

Trong một repository, hook mặc định nằm trong thư mục hooks bên dưới Git directory. Với repository thường, thư mục đó thường là .git/hooks. Với bare repository, hooks nằm trong Git directory của repository bare.

Để hỏi Git đường dẫn chính xác:

~~~bash
git rev-parse --git-path hooks
~~~

Không nên luôn tự ghép đường dẫn .git/hooks vì linked worktree, submodule hoặc cấu trúc Git directory riêng có thể dùng đường dẫn khác.

### core.hooksPath

Git cho phép chỉ định một thư mục hooks khác:

~~~bash
git config --show-origin --get core.hooksPath
~~~

Nếu key này được đặt, Git tìm hook trong thư mục đã cấu hình thay cho hooks directory mặc định. Có thể đặt ở repository:

~~~bash
git config --local core.hooksPath .githooks
~~~

Khi dùng đường dẫn tương đối, đường dẫn được phân giải theo working directory của Git khi chạy. Nhóm nên thống nhất cách bố trí và tài liệu cài đặt để mọi người dùng cùng hook.

### Hook có được chia sẻ khi clone không?

Các hook nằm trong Git directory không được commit như source code thông thường và không tự động được chuyển sang người clone repository. Vì vậy, nếu muốn chia sẻ hook client-side, nhóm thường lưu script trong thư mục được version control, ví dụ .githooks, rồi hướng dẫn thành viên đặt core.hooksPath trỏ đến đó hoặc dùng công cụ cài đặt.

Server-side hooks phải được cài trên repository nhận push hoặc do nền tảng quản lý. Commit file hook trong repository client không tự cài hook trên server.

## 10. Quyền thực thi và quy tắc viết hook

Trên hệ thống Unix-like, hook cần có quyền thực thi:

~~~bash
chmod +x .githooks/pre-push
chmod +x hooks/pre-receive
~~~

Đường dẫn thực tế tùy hooksPath và loại repository. Trên Windows, Git for Windows thường chạy hook shell qua môi trường đi kèm; hãy kiểm tra interpreter, line ending và quyền truy cập theo môi trường triển khai.

Một hook tốt nên:

- Kết thúc với mã 0 khi cho phép thao tác; mã khác 0 khi cần từ chối ở hook có quyền từ chối.
- Gửi lý do lỗi ngắn gọn và có thể hành động qua stderr.
- Đọc stdin theo định dạng hook quy định, không giả định chỉ có một ref.
- Xử lý ref tạo mới và xóa ref, trong đó OID bằng chuỗi số 0.
- Không giả định hash có độ dài cố định.
- Chạy nhanh, tránh chờ tương tác không cần thiết.
- Ghi log phù hợp nhưng không làm lộ token, mật khẩu hoặc dữ liệu nhạy cảm.
- Có kiểm thử và phiên bản rõ ràng nếu được dùng làm chính sách chung.

Nếu hook cần gọi API hoặc hệ thống ngoài, hãy xử lý timeout, retry và lỗi mạng. Đặc biệt với post-receive, nên ghi nhận công việc cần làm vào hàng đợi bền vững để có thể retry nếu dịch vụ ngoài tạm thời không hoạt động.

## 11. Xem hook mẫu và kiểm tra hook đang áp dụng

Git thường tạo các file mẫu có hậu tố .sample trong hooks directory. Chúng không được chạy chỉ vì tồn tại; cần bỏ hậu tố và cấu hình đúng nội dung, quyền thực thi.

Liệt kê hooks directory:

~~~bash
git rev-parse --git-path hooks
~~~

Kiểm tra hooksPath:

~~~bash
git config --show-origin --get core.hooksPath
~~~

Kiểm tra trạng thái repository trước khi thử hook:

~~~bash
git status -sb
git remote -v
~~~

Nếu hook không chạy như mong đợi, kiểm tra:

1. Tên file có đúng tên hook và không còn hậu tố .sample không?
2. Git đang dùng hooks directory mặc định hay core.hooksPath?
3. Script có quyền thực thi và interpreter hợp lệ không?
4. Script có lỗi cú pháp hoặc phụ thuộc chương trình không có trong PATH không?
5. Hook có bị bỏ qua bằng --no-verify hoặc cấu hình của công cụ gọi Git không?
6. Hook nằm ở client hay server? Bạn đang kiểm tra đúng máy chưa?

## 12. Kiểm thử hành vi từng hook

Không nên thử hook trên branch production hoặc repository dùng chung ngay lần đầu. Tạo repository thử nghiệm local hoặc bare repository riêng để quan sát hành vi.

### Thử pre-push

Tạo một script pre-push trả mã khác 0:

~~~sh
#!/bin/sh
echo "Push blocked by local test hook" >&2
exit 1
~~~

Chạy git push và xác nhận client dừng trước khi remote ref thay đổi. Sau đó thử với git push --no-verify để hiểu hook client có thể bị bỏ qua như thế nào. Chỉ thực hiện trong repository thử nghiệm.

### Thử pre-receive

Trong bare repository nhận, cài pre-receive trả mã khác 0. Push một branch thử nghiệm và xác nhận toàn bộ cập nhật trong lần push bị từ chối. Không dùng ví dụ từ chối toàn bộ này trên remote đang phục vụ nhóm.

### Thử update với nhiều ref

Tạo hai branch thử nghiệm và cài update để từ chối một branch theo tên. Push cả hai ref cùng lúc. Quan sát rằng ref bị hook từ chối không được cập nhật, trong khi ref còn lại có thể thành công nếu không có lỗi khác.

### Thử post-receive

Cài post-receive ghi old OID, new OID và ref name vào log. Push branch thử nghiệm và xác nhận log được ghi sau khi ref remote thay đổi. Có thể thử để hook trả mã khác 0 rồi kiểm tra rằng ref vẫn giữ commit đã nhận.

## 13. Những nhầm lẫn thường gặp

### pre-push và pre-receive có giống nhau?

Không. pre-push chạy ở client trước khi push được gửi. pre-receive chạy trên server khi nhận push và có thể áp dụng chính sách tập trung cho repository nhận.

### pre-receive chạy một lần cho từng branch?

Không. Nó chạy một lần cho lần nhận và nhận danh sách tất cả ref qua stdin. update mới là hook được gọi riêng cho từng ref.

### update từ chối một ref có làm hủy mọi ref khác không?

Không nhất thiết. update từ chối ref mà lần gọi đó đang kiểm tra. Những ref khác có thể vẫn được cập nhật. Nếu cần tính toàn vẹn cho cả nhóm ref, dùng pre-receive để kiểm tra trước và từ chối toàn bộ lần nhận.

### post-receive có thể hủy push nếu deploy thất bại?

Không. Hook chạy sau khi ref đã được cập nhật. Nếu deploy thất bại, cần ghi nhận và retry tác vụ vận hành; push vẫn đã được chấp nhận.

### Hook client-side có tự được chia sẻ khi clone?

Không. Hook trong Git directory không nằm trong lịch sử commit thông thường. Muốn chia sẻ, cần lưu script trong repository và có bước cài đặt; chính sách bắt buộc nên được thực thi ở server.

### Có thể dùng --no-verify để bỏ qua mọi hook?

Không nên hiểu như vậy. --no-verify áp dụng cho một số hook client-side, chẳng hạn pre-push. Nó không cho client bỏ qua pre-receive, update hoặc post-receive đang được server thực thi.

## 14. Tự kiểm tra

Một nhóm muốn xây dựng quy trình:

- Máy phát triển chạy test trước khi push.
- Server từ chối mọi lần push nếu một trong các ref vi phạm chính sách.
- Server không cho xóa branch release.
- Khi main được cập nhật, hệ thống CI nhận sự kiện để triển khai.

Hãy trả lời:

1. Hook nào nên chạy test ở máy phát triển?
2. Hook nào kiểm tra toàn bộ ref và từ chối toàn bộ lần push?
3. Hook nào có thể từ chối riêng một branch release?
4. Hook nào chạy sau khi main đã cập nhật?
5. Dữ liệu pre-push nhận qua đối số và stdin gồm những gì?
6. Vì sao không nên đặt kiểm tra bắt buộc ở post-receive?
7. Vì sao chính sách server-side không nên chỉ dựa vào pre-push?

**Gợi ý:** Dùng pre-push cho test phía client; pre-receive cho chính sách áp dụng toàn bộ lần nhận; update cho quy tắc riêng từng ref; post-receive để gửi sự kiện triển khai sau cập nhật. pre-push nhận tên remote, URL và các dòng local-ref/local-OID/remote-ref/remote-OID. post-receive không thể hoàn tác push đã thành công. Người dùng có thể không cài hoặc bỏ qua hook client-side, nên quy tắc bắt buộc phải nằm ở server.

## Kết luận

pre-push chạy ở client để kiểm tra trước khi gửi; pre-receive chạy một lần ở server để xem toàn bộ ref và có thể từ chối toàn bộ lần nhận; update chạy riêng từng ref và chỉ từ chối ref tương ứng; post-receive chạy sau khi ref được cập nhật để thông báo hoặc kích hoạt công việc tiếp theo. Hãy chọn hook theo đúng thời điểm và phạm vi quyết định, đọc đúng dữ liệu đầu vào, giữ hook ngắn và có thông báo rõ ràng. Đặc biệt, đặt chính sách bắt buộc ở server và xem post-receive là điểm khởi chạy công việc sau push, không phải nơi kiểm duyệt hay hoàn tác push.
