# Xác minh chữ ký, nguồn tin cậy và giới hạn của chữ ký

Trong một repository dùng chung, commit và tag có thể được ký bằng khóa mật mã để người nhận kiểm tra nội dung có được ký bởi khóa tương ứng hay không. Chữ ký giúp phát hiện việc nội dung commit/tag bị thay đổi sau khi ký và cung cấp bằng chứng về khóa đã tạo chữ ký. Tuy nhiên, một chữ ký hợp lệ không tự động chứng minh người đứng sau khóa là đúng người, người đó được phép thay đổi branch, hoặc mã nguồn an toàn.

Khi kiểm tra chữ ký Git, cần tách ba câu hỏi: **chữ ký có hợp lệ về mật mã không**, **khóa hoặc danh tính ký có thuộc nguồn tin cậy không**, và **người ký có được phép ký loại thay đổi này theo chính sách của dự án không**. Các lệnh `git verify-commit`, `git verify-tag` và `git log --show-signature` giúp kiểm tra chữ ký; việc xác nhận khóa và áp dụng chính sách cần thêm nguồn thông tin đáng tin cậy.

## 1. Git có thể ký những đối tượng nào?

Git hỗ trợ chữ ký cho commit và annotated tag. Chữ ký được lưu trong đối tượng Git và được xác minh dựa trên nội dung đã ký cùng khóa công khai tương ứng.

- **Signed commit:** commit chứa chữ ký trong metadata. Chữ ký gắn với nội dung commit, bao gồm tree, parent, author, committer và thông điệp commit.
- **Signed annotated tag:** tag object chứa metadata tagger, thông điệp, đối tượng đích và chữ ký. Đây là cách phổ biến để ký một mốc phát hành.
- **Lightweight tag:** chỉ là ref trỏ đến object, không có tag object riêng nên không thể gắn chữ ký tag theo cách `git tag -s` thực hiện.

Một commit đã ký có thể được kiểm tra độc lập với branch đang trỏ đến nó. Một annotated tag đã ký xác nhận người giữ khóa đã ký nội dung tag và đối tượng mà tag trỏ tới. Điều đó không có nghĩa mọi commit trong lịch sử phía trước đều đã được ký.

## 2. Phân biệt chữ ký hợp lệ, danh tính và quyền hạn

Kết quả xác minh chữ ký cần được hiểu theo từng lớp:

| Câu hỏi | Điều cần kiểm tra | Điều chưa thể kết luận chỉ từ chữ ký |
|---|---|---|
| Chữ ký có hợp lệ không? | Chữ ký khớp với nội dung đối tượng và khóa công khai | Người giữ khóa là ai ngoài đời hoặc trong tổ chức |
| Khóa có đáng tin cậy không? | Fingerprint/principal/certificate khớp nguồn tin cậy và chưa bị thu hồi theo chính sách | Người đó có quyền review, merge hoặc phát hành hay không |
| Người ký có được phép không? | Danh sách signer được phép, phạm vi trách nhiệm, thời điểm và quy trình phê duyệt | Mã nguồn không có lỗ hổng hoặc hành vi độc hại |

Ví dụ, `git verify-commit` có thể xác nhận chữ ký hợp lệ với một khóa OpenPGP. Nhưng nếu bạn lấy khóa công khai từ một trang không xác thực, kẻ tấn công có thể đưa cho bạn khóa của họ và tự ký commit. Chữ ký vẫn đúng về mặt mật mã, trong khi danh tính được gán cho khóa có thể sai.

Vì vậy, cần xác nhận khóa bằng fingerprint hoặc danh tính từ nguồn độc lập đáng tin cậy, rồi đối chiếu với chính sách dự án. Không dùng riêng tên hiển thị hoặc email trong commit làm bằng chứng danh tính: các trường này là dữ liệu commit và người tạo commit có thể khai báo giá trị của chúng.

## 3. Các định dạng chữ ký Git hỗ trợ

Git có thể dùng nhiều backend ký và xác minh. Định dạng được chọn qua cấu hình `gpg.format`.

| Giá trị `gpg.format` | Cơ chế | Công cụ thường dùng |
|---|---|---|
| `openpgp` | Chữ ký OpenPGP | GnuPG (`gpg`) |
| `ssh` | Chữ ký SSH | `ssh-keygen` và SSH keys |
| `x509` | Chữ ký X.509 | `gpgsm` cùng hạ tầng chứng thư phù hợp |

Nếu không cấu hình, Git mặc định dùng `openpgp`. Cấu hình và công cụ xác minh phải nhất quán giữa máy tạo chữ ký và máy kiểm tra. Một máy có thể xác minh commit OpenPGP nhưng chưa được cấu hình để xác minh SSH hoặc X.509.

Kiểm tra cấu hình hiện tại:

```bash
git config --show-origin --get gpg.format
git config --show-origin --get gpg.program
git config --show-origin --get user.signingkey
```

Không phải mọi khóa hoặc chứng thư đều dùng được với mọi định dạng. Hãy xác định dự án yêu cầu loại chữ ký nào trước khi cấu hình.

## 4. Xác minh một commit bằng git verify-commit

Để kiểm tra chữ ký của một commit:

```bash
git verify-commit <commit>
```

Ví dụ:

```bash
git verify-commit HEAD
git verify-commit a1b2c3d
```

Nếu commit có chữ ký và cấu hình xác minh phù hợp, Git gọi chương trình tương ứng để kiểm tra. Khi chữ ký hợp lệ, output có thể cho biết chữ ký tốt và thông tin khóa hoặc signer. Nếu commit không có chữ ký, chữ ký sai, khóa không được tìm thấy hoặc verifier không được cấu hình đúng, lệnh sẽ không xác minh thành công.

Để xem thêm thông tin từ verifier:

```bash
git verify-commit --verbose HEAD
```

Với OpenPGP, thông báo từ GnuPG có thể phân biệt chữ ký hợp lệ với mức độ tin cậy mà keyring gán cho khóa. Hãy đọc toàn bộ output; dòng “Good signature” chỉ xác nhận chữ ký khớp với khóa công khai được dùng để kiểm tra. Nó không thay thế việc xác nhận fingerprint và quyền của người ký.

## 5. Xác minh chữ ký tag bằng git verify-tag

Để kiểm tra một annotated tag:

```bash
git verify-tag v2.4.0
```

Có thể dùng `--verbose` để xem thêm thông tin verifier:

```bash
git verify-tag --verbose v2.4.0
```

Lệnh này xác minh chữ ký của tag object. Lightweight tag không có tag object và chữ ký riêng, nên không thể xác minh bằng cách này.

Có thể xem nội dung tag cùng chữ ký bằng:

```bash
git show --show-signature v2.4.0
```

Một tag ký hợp lệ là bằng chứng rằng khóa đã ký tag object trỏ đến đối tượng đích. Nếu tag trỏ đến commit phát hành, hãy kiểm tra thêm commit đó và các điều kiện release mà nhóm yêu cầu. Chữ ký tag không tự động ký thay cho từng commit trước đó.

## 6. Xem chữ ký trong lịch sử bằng git log --show-signature

Khi cần rà soát một dải commit, có thể hiển thị thông tin chữ ký cùng lịch sử:

```bash
git log --show-signature --oneline --decorate -10
```

Hoặc xem một branch cụ thể:

```bash
git log --show-signature --format=fuller origin/main
```

`--show-signature` yêu cầu Git hiển thị thông tin xác minh chữ ký của các commit có chữ ký trong phần lịch sử được xem. Commit không có chữ ký sẽ không có thông tin chữ ký để hiển thị. Việc hiển thị không đồng nghĩa chính sách của dự án đã được thỏa mãn; cần kiểm tra signer, phạm vi commit và quy tắc bắt buộc.

Để xác minh một tập commit một cách rõ ràng trong quy trình tự động, có thể lặp qua các mã commit đã chọn và gọi `git verify-commit` cho từng commit. Phải xác định chính xác phạm vi lịch sử cần kiểm tra, ví dụ các commit mới trên branch tính năng so với base branch; không mặc định chỉ commit đầu branch là đủ.

## 7. Xác nhận khóa OpenPGP bằng fingerprint

Với OpenPGP, không nên chỉ so sánh tên hoặc email hiển thị trong output. Hãy lấy fingerprint đầy đủ của khóa công khai và xác nhận nó qua một kênh độc lập.

Liệt kê khóa cùng fingerprint:

```bash
gpg --list-keys --fingerprint
```

Xem fingerprint của một khóa cụ thể:

```bash
gpg --fingerprint <key-id-or-email>
```

Sau đó đối chiếu fingerprint với nguồn được tổ chức tin cậy công bố, chẳng hạn danh bạ khóa ký nội bộ, tài liệu bảo mật đã xác thực hoặc người phụ trách release qua một kênh liên lạc đã xác minh. Key ID ngắn có thể trùng hoặc không đủ để xác định duy nhất khóa; fingerprint đầy đủ là giá trị cần so sánh.

GnuPG có mô hình trust riêng để biểu diễn mức độ tin cậy vào khóa và liên kết danh tính. Một chữ ký hợp lệ có thể đi kèm cảnh báo rằng khóa chưa được chứng nhận hoặc chưa được tin cậy. Không nên tắt kiểm tra trust chỉ để làm cảnh báo biến mất; hãy xác nhận chủ sở hữu khóa và áp dụng quy trình tin cậy của tổ chức.

## 8. Xác minh chữ ký SSH bằng allowed signers

Git hỗ trợ dùng SSH key để ký commit và tag. Khóa SSH dùng để xác minh chữ ký cần được liên kết với một principal (danh tính) được phép thông qua file `allowedSignersFile`.

Ví dụ file `~/.ssh/allowed_signers`:

```text
dev@example.com namespaces="git" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExamplePublicKeyMaterial
release@example.com namespaces="git" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAnotherPublicKeyMaterial
```

Các chuỗi khóa ở trên chỉ là minh họa, không phải khóa có thể dùng thật. Mỗi dòng gồm principal, các tùy chọn nếu có, loại khóa và public key. Principal cần khớp danh tính mà dự án quy định cho signer; `namespaces="git"` giới hạn khóa vào namespace chữ ký Git.

Cấu hình file cho repository hoặc người dùng:

```bash
git config --global gpg.format ssh
git config --global gpg.ssh.allowedSignersFile ~/.ssh/allowed_signers
```

Sau khi cấu hình, xác minh commit:

```bash
git verify-commit HEAD
```

File allowed signers là danh sách khóa được chấp nhận cho xác minh theo cấu hình local. Nếu một khóa bị thu hồi hoặc không còn được phép, cần cập nhật chính sách và cơ chế thu hồi phù hợp; không giữ khóa cũ trong danh sách chỉ vì các commit lịch sử từng dùng nó.

Với SSH, “khóa có trong allowed signers” là quyết định tin cậy do người quản trị file đưa ra. Nó không tự chứng minh principal là nhân viên nào hoặc có quyền phê duyệt release nào. Nguồn khóa và việc quản lý file này phải được bảo vệ, review và cập nhật.

## 9. Xác minh chứng thư X.509

Git cũng hỗ trợ chữ ký X.509 thông qua định dạng `x509`, thường dùng `gpgsm` để ký và xác minh. Trong mô hình này, việc tin cậy phụ thuộc vào chứng thư, chuỗi chứng thực, CA và trust store được cấu hình trên hệ thống.

Kiểm tra định dạng:

```bash
git config --get gpg.format
```

Nếu dự án dùng X.509, cần có công cụ phù hợp và cấu hình chứng thư/CA theo chính sách của tổ chức. Chữ ký có thể hợp lệ theo khóa trong chứng thư nhưng vẫn cần kiểm tra chuỗi chứng thực, thời hạn, trạng thái thu hồi và danh tính subject. Không nên tự thêm CA hoặc chứng thư lạ vào trust store chỉ để một commit được xác minh thành công.

## 10. Kiểm tra nguồn tin cậy của signer

Một quy trình xác minh đáng tin cậy cần có nguồn gốc rõ ràng cho khóa hoặc chứng thư. Các nguồn có thể dùng:

- Danh bạ khóa ký hoặc fingerprint được đội bảo mật/release công bố trong hệ thống nội bộ đã xác thực.
- Tài liệu chính thức của dự án, được truy cập qua domain và kênh phân phối đã xác minh.
- Chứng thư do CA nội bộ hoặc CA công khai được tổ chức tin cậy cấp, với chuỗi chứng thực hợp lệ.
- SSH allowed signers file được quản lý tập trung, có review và lịch sử cập nhật.
- Xác nhận fingerprint qua một kênh độc lập với nơi bạn tải commit hoặc khóa công khai.

Không nên tin cậy khóa chỉ vì:

- Khóa được đính kèm trong cùng pull request chứa commit cần xác minh.
- Email hoặc tên người ký giống tên đồng nghiệp.
- Key ID ngắn trùng với thông tin trong một log không xác thực.
- Một trang mirror hoặc file đính kèm không có nguồn gốc rõ ràng cung cấp public key.

Nếu kẻ tấn công kiểm soát cả commit và nguồn khóa bạn dùng để xác nhận, phép so sánh không độc lập. Hãy lấy fingerprint hoặc principal từ nguồn đã được xác thực trước đó.

## 11. Chữ ký không thay thế quyền truy cập và review

Chữ ký trả lời câu hỏi “khóa nào đã ký nội dung này?” trong phạm vi cơ chế xác minh. Nó không tự trả lời:

- Người ký có quyền push vào `main` hay không.
- Commit đã được review hoặc CI pass chưa.
- Người ký có quyền tạo release hoặc ký tag phiên bản hay không.
- Tệp trong commit có chứa mã độc, secret hoặc lỗ hổng hay không.
- Artifact được build từ commit này có đúng là artifact được triển khai hay không.

Các điều kiện đó cần cơ chế riêng như quyền repository, branch protection, pull request review, CI, release approval và provenance/attestation của build. Ví dụ, một contributor có thể ký commit hợp lệ bằng khóa của họ nhưng vẫn không có quyền merge vào branch bảo vệ.

Đối với release, nhóm có thể yêu cầu cả commit/tag được ký, signer thuộc danh sách release managers, pipeline thành công và artifact có provenance phù hợp. Mỗi điều kiện phải được kiểm tra riêng theo chính sách.

## 12. Chữ ký commit/tag khác chữ ký push

Git còn có cơ chế ký yêu cầu push. Ví dụ:

```bash
git push --signed origin main
```

Chữ ký push tạo chứng thư cho yêu cầu cập nhật ref trong lần push. Nó khác với chữ ký nằm trong commit hoặc annotated tag:

| Loại chữ ký | Xác nhận điều gì? | Được lưu ở đâu? |
|---|---|---|
| Commit signature | Nội dung commit được ký bởi khóa | Trong commit object |
| Tag signature | Nội dung annotated tag và đối tượng đích được ký | Trong tag object |
| Push certificate | Yêu cầu cập nhật ref của lần push được ký | Được gửi trong giao thức push tới server hỗ trợ |

Server cần hỗ trợ và cấu hình cơ chế nhận push certificate thì chữ ký push mới có thể được xử lý theo chính sách. Chữ ký push không thay thế chữ ký commit/tag; ngược lại, commit đã ký cũng không chứng minh yêu cầu push đến server được ký.

## 13. Ví dụ quy trình kiểm tra một release

Giả sử nhóm nhận tag `v3.2.0` và cần xác minh trước khi triển khai.

```bash
# 1. Xem thông tin tag và chữ ký.
git show --show-signature v3.2.0

# 2. Xác minh chữ ký tag object.
git verify-tag --verbose v3.2.0

# 3. Xác định commit mà tag trỏ đến.
git rev-parse 'v3.2.0^{commit}'

# 4. Xác minh chữ ký của commit đích nếu chính sách yêu cầu.
git verify-commit 'v3.2.0^{commit}'

# 5. Xem lịch sử và chữ ký của các commit liên quan.
git log --show-signature --oneline -20 'v3.2.0^{commit}'
```

Sau các bước kỹ thuật, đối chiếu fingerprint hoặc principal của signer với danh sách phát hành tin cậy. Kiểm tra tag có trỏ đúng commit dự kiến, branch/release đã được review và CI đạt yêu cầu. Nếu dự án yêu cầu mọi commit trong một khoảng phải ký, xác minh từng commit trong khoảng đó thay vì chỉ xác minh commit đích.

Nếu chữ ký không xác minh được, dừng quy trình phát hành và tìm nguyên nhân: thiếu public key, sai định dạng `gpg.format`, verifier chưa được cài, khóa hết hạn/bị thu hồi hoặc nội dung đã thay đổi. Không bỏ qua cảnh báo chỉ để tiếp tục triển khai.

## 14. Những lỗi và cảnh báo thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Commit không có signature | Commit được tạo mà không ký | Xác định chính sách có bắt buộc ký hay không; không thể xác minh chữ ký chưa tồn tại |
| Không tìm thấy public key | Máy xác minh chưa có khóa tương ứng | Lấy khóa từ nguồn tin cậy, xác minh fingerprint rồi import/cấu hình |
| Chữ ký không hợp lệ | Nội dung bị thay đổi, chữ ký hỏng hoặc dùng sai verifier | Kiểm tra commit/tag, định dạng chữ ký và công cụ xác minh |
| Good signature nhưng cảnh báo trust | Chữ ký hợp lệ nhưng keyring chưa tin cậy danh tính | Xác minh fingerprint qua nguồn độc lập và xử lý trust theo chính sách |
| SSH signature không xác minh được | Thiếu hoặc sai `gpg.ssh.allowedSignersFile`, principal không khớp hoặc khóa không được phép | Kiểm tra allowed signers và principal được dự án công bố |
| X.509 chain không được tin cậy | Thiếu CA, trust store hoặc chứng thư có vấn đề | Xác minh chuỗi chứng thực và trạng thái chứng thư theo chính sách tổ chức |
| Tag verify không hoạt động với lightweight tag | Lightweight tag không có tag object/signature | Dùng annotated tag đã ký nếu cần xác nhận release |
| Chữ ký hợp lệ nhưng policy từ chối | Signer không nằm trong danh sách được phép hoặc thiếu review/CI | Kiểm tra quyền và các điều kiện chính sách riêng |

## 15. Ghi nhớ

Để xác minh commit, dùng `git verify-commit`; để xác minh annotated tag, dùng `git verify-tag`; để xem chữ ký cùng lịch sử, dùng `git log --show-signature`. Git hỗ trợ OpenPGP, SSH và X.509, nhưng máy xác minh phải được cấu hình đúng định dạng và nguồn khóa/chứng thư.

Chữ ký hợp lệ chứng minh nội dung khớp với khóa dùng để ký. Muốn tin cậy danh tính, phải xác nhận fingerprint, principal hoặc chứng thư từ nguồn độc lập. Muốn xác nhận quyền thực hiện thay đổi, vẫn cần kiểm tra quyền repository, review, CI và chính sách release. Chữ ký là một lớp bảo vệ quan trọng của lịch sử Git, không phải bằng chứng toàn diện rằng người ký được phép hoặc nội dung an toàn.
