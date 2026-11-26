1. Opaque access token thường có đặc điểm nào?
A. Tham chiếu không tự chứa claims có thể đọc.
B. Chuỗi JSON được ký để client tự đọc claims.
C. Bản mã có thể giải bằng khóa bí mật của client.
D. Mã định danh user được gửi kèm password.
Đáp án đúng: A

2. Resource Server nên xử lý chuỗi opaque token như thế nào?
A. Tách header và payload như JWT trước khi xác minh.
B. Giải mã token bằng client secret của Resource Server.
C. Suy ra user và scope từ tiền tố của chuỗi token.
D. Coi là bearer credential và gọi introspection.
Đáp án đúng: D

3. JWT khác opaque token chủ yếu ở điểm nào?
A. JWT tự chứa claims; opaque cần tra trạng thái.
B. JWT luôn cần introspection; opaque luôn kiểm tra cục bộ.
C. JWT không có chữ ký; opaque token luôn được ký số.
D. Hai loại token có cùng cách xác minh và thu hồi.
Đáp án đúng: A

4. Lợi ích chính của opaque token trong quản lý trạng thái tập trung là gì?
A. Resource Server có thể xác minh token mà không liên lạc.
B. Client có thể đọc mọi claims mà không cần khóa.
C. AS có thể đổi trạng thái token tập trung.
D. Token tự hết hạn ngay khi người dùng đóng trình duyệt.
Đáp án đúng: C

5. Trong phản hồi introspection, active=true thường biểu thị điều gì?
A. AS xác nhận token hiện còn hiệu lực.
B. Token được phép gọi mọi API trong hệ thống.
C. Người dùng có role quản trị trên mọi tenant.
D. Token đã được ký bằng thuật toán mạnh nhất.
Đáp án đúng: A

6. Một token active=true có scope read:orders nhưng gọi API delete. Resource Server nên làm gì?
A. Cho phép vì active=true xác nhận mọi quyền.
B. Gọi lại introspection đến khi scope thay đổi.
C. Từ chối vì scope không cho phép delete.
D. Bỏ qua scope vì token opaque không có claims.
Đáp án đúng: C

7. Introspection trả active=false. Resource Server nên xử lý thế nào?
A. Từ chối, không suy đoán lý do inactive.
B. Cho phép request nếu token chưa tới exp.
C. Thử giải mã token như JWT trước khi quyết định.
D. Chấp nhận token nếu client gửi thêm username.
Đáp án đúng: A

8. Ai thường được phép gọi introspection endpoint của Authorization Server?
A. Bất kỳ client nào nắm được một access token.
B. Resource Server đã đăng ký và xác thực.
C. Người dùng cuối chưa đăng nhập vào ứng dụng.
D. Mọi máy trong mạng nội bộ không cần credential.
Đáp án đúng: B

9. Khi xác thực Resource Server tại introspection endpoint, điều gì phù hợp?
A. Dùng client authentication đã đăng ký.
B. Dùng access token đang kiểm tra làm client secret.
C. Chỉ gửi tên API trong query string không xác thực.
D. Dựa vào IP nguồn thay cho client authentication.
Đáp án đúng: A

10. Theo OAuth Token Introspection, request thường truyền token theo cách nào?
A. GET với token đặt trong URL path.
B. POST JSON bắt buộc có password người dùng.
C. POST form-encoded với tham số token.
D. Header Cookie chứa token và không cần body.
Đáp án đúng: C

11. Trường token_type_hint trong introspection request có vai trò gì?
A. Chứng minh token đã được cấp đúng audience.
B. Bắt buộc khai báo thuật toán ký của JWT.
C. Thay thế tham số token trong request.
D. Gợi ý loại token để AS tra cứu.
Đáp án đúng: D

12. Trường nào là bắt buộc trong phản hồi introspection chuẩn?
A. aud luôn chứa đúng một Resource Server.
B. scope luôn liệt kê mọi quyền của user.
C. active boolean biểu thị trạng thái token.
D. username luôn có mặt cả với token machine-to-machine.
Đáp án đúng: C

13. Resource Server nên kiểm tra audience trong phản hồi introspection để làm gì?
A. Xác định Authorization Server có đang hoạt động hay không.
B. Suy ra token được lưu trong cache bao lâu.
C. Chọn thuật toán mã hóa cho response body.
D. Đảm bảo token được phát hành cho API này.
Đáp án đúng: D

14. Khi xử lý scope từ introspection response, Resource Server cần làm gì?
A. So quyền endpoint với scope được cấp trước khi xử lý.
B. Coi mọi scope tương đương quyền truy cập đầy đủ.
C. Chỉ kiểm tra scope khi token đã hết hạn.
D. Dùng scope thay cho kiểm tra tenant và object ownership.
Đáp án đúng: A

15. Vì sao Resource Server vẫn cần kiểm tra thời hạn token?
A. Introspection luôn đảm bảo token không bao giờ hết hạn.
B. Không dùng trước nbf hoặc sau exp của token.
C. Opaque token không thể có thời hạn được cấp.
D. Thời hạn chỉ có ý nghĩa với JWT tự chứa.
Đáp án đúng: B

16. Revocation endpoint và introspection endpoint khác nhau thế nào?
A. Revocation đọc scope; introspection đổi trạng thái token.
B. Cả hai đều cấp access token mới cho client.
C. Introspection thu hồi token còn revocation chỉ kiểm tra.
D. Revocation yêu cầu thu hồi; introspection hỏi trạng thái.
Đáp án đúng: D

17. Sau khi Authorization Server thu hồi token, điều gì có thể làm request vẫn được chấp nhận?
A. Token opaque tự chuyển thành JWT sau khi bị thu hồi.
B. Audience tự mở rộng khi Authorization Server ngừng hoạt động.
C. Cache vẫn giữ kết quả active cũ sau khi token bị revoke.
D. Resource Server không cần kiểm tra active của token.
Đáp án đúng: C

18. Positive introspection cache nên chọn TTL dựa trên yếu tố nào?
A. Giới hạn stale window chấp nhận được sau revoke.
B. Thời gian uptime trung bình của máy chủ API.
C. Độ dài chuỗi token và số ký tự ngẫu nhiên.
D. Thời gian sống của phiên đăng nhập trình duyệt.
Đáp án đúng: A

19. Giới hạn nào nên áp dụng cho TTL của kết quả active=true?
A. Luôn dài hơn thời hạn token để giảm số lần gọi.
B. Cố định nhiều ngày cho mọi loại token.
C. Không vượt exp và stale budget đã định.
D. Không cần giới hạn nếu cache đặt trong mạng riêng.
Đáp án đúng: C

20. Negative cache cho active=false nên được thiết kế ra sao?
A. TTL dài vô hạn vì token inactive không thể đổi trạng thái.
B. TTL ngắn, giới hạn dung lượng và số entry.
C. Không giới hạn số entry để lưu mọi chuỗi ngẫu nhiên.
D. Dùng chung positive cache mà không phân biệt trạng thái.
Đáp án đúng: B

21. Để giảm lộ bearer token trong cache, nên dùng cách nào?
A. Ghi token thô vào key để dễ điều tra sự cố.
B. Dùng digest làm cache key, bảo vệ cache.
C. Dùng tiền tố token làm cache key cho mọi issuer.
D. Lưu token trong metric label để tra cứu nhanh.
Đáp án đúng: B

22. Khi nhận sự kiện revoke từ Authorization Server, Resource Server nên làm gì?
A. Chờ TTL hết hạn dù có cơ chế invalidation.
B. Gia hạn entry active để tránh tăng tải introspection.
C. Xóa toàn bộ cache của mọi tenant, node và issuer ngay lập tức.
D. Xóa entry cache liên quan khi nhận revoke event.
Đáp án đúng: D

23. Trong hệ thống nhiều vùng, vì sao cache invalidation cần xét consistency?
A. Mọi vùng luôn chia sẻ cùng bộ nhớ cache tức thời.
B. Revoke event có thể đến trễ hoặc mất giữa các vùng.
C. Token opaque không thể được dùng qua nhiều vùng.
D. Consistency chỉ ảnh hưởng dữ liệu nghiệp vụ, không ảnh hưởng auth.
Đáp án đúng: B

24. Timeout cho introspection nên được cấu hình thế nào?
A. Vô hạn để chờ Authorization Server phục hồi.
B. Dài hơn thời hạn access token đang được kiểm tra.
C. Bằng timeout của mọi dịch vụ downstream.
D. Nằm trong ngân sách latency của request.
Đáp án đúng: D

25. Khi introspection gặp lỗi mạng tạm thời, retry nên áp dụng ra sao?
A. Retry liên tục đến khi có phản hồi thành công.
B. Retry cả active=false như lỗi truyền tải.
C. Retry giới hạn, backoff và lỗi tạm thời.
D. Retry không giới hạn để tránh từ chối user hợp lệ.
Đáp án đúng: C

26. Circuit breaker giúp ích gì khi Authorization Server gặp sự cố?
A. Bỏ qua xác minh token cho đến khi server hoạt động lại.
B. Tự gia hạn mọi cache active không giới hạn.
C. Thay client authentication tại introspection endpoint.
D. Ngắt retry lặp, chờ ổn định rồi thăm dò phục hồi.
Đáp án đúng: D

27. Với thao tác nhạy cảm, chính sách nào an toàn khi introspection không khả dụng?
A. Fail open và cho phép mọi token từng active.
B. Bỏ kiểm tra scope nhưng vẫn kiểm tra định dạng token.
C. Fail closed khi không xác minh được token.
D. Chấp nhận token nếu client gửi lại cùng request.
Đáp án đúng: C

28. Rate limiting introspection endpoint nên được áp dụng thế nào?
A. Chỉ giới hạn theo IP công cộng của người dùng cuối.
B. Giới hạn theo Resource Server/client.
C. Tắt giới hạn vì introspection chỉ đọc trạng thái token.
D. Chỉ giới hạn active=false, không giới hạn request khác.
Đáp án đúng: B

29. Cache introspection trong môi trường multi-tenant cần phân tách theo gì?
A. Issuer, Resource Server và tenant context.
B. Chỉ chuỗi token vì mọi tenant dùng chung quyền.
C. Chỉ username vì token luôn gắn một người dùng.
D. Chỉ hostname của node đang giữ cache.
Đáp án đúng: A

30. Token của tenant A có audience đúng API nhưng thuộc tenant B. API nên làm gì?
A. Cho phép vì audience đã khớp API nhận request.
B. Từ chối khi tenant không khớp tài nguyên.
C. Đổi tenant trong cache key rồi tiếp tục xử lý.
D. Bỏ qua tenant vì introspection trả active=true.
Đáp án đúng: B

31. Opaque bearer token bị ghi vào access log. Rủi ro chính là gì?
A. Token tự hết hạn ngay khi xuất hiện trong log.
B. Log làm thay đổi audience và scope của token.
C. Người đọc log có thể dùng token như bearer.
D. Token bị ghi log sẽ tự chuyển sang inactive.
Đáp án đúng: C

32. Biện pháp nào giảm nguy cơ lộ token trong telemetry?
A. Ghi toàn bộ token trong trace để hỗ trợ correlation.
B. Redact Authorization header; tránh token labels.
C. Chỉ che ba ký tự cuối của token trong log.
D. Đưa token vào metric label nhưng đặt retention ngắn.
Đáp án đúng: B

33. Nhóm vận hành nên theo dõi chỉ số nào cho introspection?
A. Giá trị token, username và password từng request.
B. Số ký tự token và nội dung header Authorization.
C. CPU của client mà không theo dõi Authorization Server.
D. Latency, errors, cache hit và active rate.
Đáp án đúng: D

34. Khi phát hiện token bị lộ, phản ứng nào phù hợp?
A. Chỉ xóa log chứa token nhưng tiếp tục chấp nhận token.
B. Gia hạn token để tránh gián đoạn người dùng hợp lệ.
C. Chuyển token bị lộ sang JWT mà không đổi credential.
D. Revoke, invalidate cache và điều tra truy cập.
Đáp án đúng: D

35. Để tương thích giữa nhiều Authorization Server, Resource Server nên dựa vào điều gì?
A. Hợp đồng introspection chuẩn và cấu hình issuer/client.
B. Định dạng tiền tố opaque token do từng nhà cung cấp tự chọn.
C. Giả định mọi server trả cùng bộ extension claims tùy biến.
D. Phân tích cấu trúc token thay cho gọi endpoint chuẩn.
Đáp án đúng: A

36. Khi introspection không cung cấp audience, Resource Server nên làm gì?
A. Cho phép vì active=true đã xác nhận đúng API.
B. Từ chối nếu không xác minh được API nhận token.
C. Dùng client_id thay cho audience trong mọi trường hợp.
D. Tự suy ra audience từ tiền tố opaque token.
Đáp án đúng: B
