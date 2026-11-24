# Media permission: quyền truy cập camera, microphone và thiết bị media

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích quy trình browser cấp quyền truy cập camera và microphone.
2. Sử dụng MediaDevices.getUserMedia() với constraints phù hợp và xử lý Promise an toàn.
3. Phân biệt secure context, quyền người dùng, Permissions Policy và authorization của ứng dụng.
4. Cấu hình Permissions-Policy và thuộc tính allow cho iframe cần truy cập media.
5. Hiểu phạm vi origin, quyền của iframe và các giới hạn khi nhúng nội dung bên thứ ba.
6. Kiểm tra trạng thái quyền bằng Permissions API khi browser hỗ trợ.
7. Liệt kê thiết bị, xử lý device change và quản lý vòng đời MediaStreamTrack.
8. Phân biệt quyền camera/microphone với quyền chia sẻ màn hình.
9. Giảm rủi ro riêng tư, XSS, ghi âm/ghi hình ngoài ý muốn và rò rỉ stream.
10. Kiểm thử media permission bằng DevTools và cài đặt quyền của browser.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. Trong WebRTC, quyền media là ranh giới quan trọng giữa website và thiết bị vật lý của người dùng. Ứng dụng cần xin đúng quyền, giải thích mục đích, kiểm soát iframe và dừng capture khi không còn cần thiết.

## 1. Media permission là gì?

Browser không cho mọi trang tự do bật camera hoặc microphone. Khi ứng dụng muốn lấy media từ thiết bị, nó gọi API Media Capture, thường là MediaDevices.getUserMedia(). Browser kiểm tra môi trường, policy và quyền người dùng rồi quyết định có cho phép hay không.

Các nguồn media phổ biến:

- Camera tích hợp trên laptop hoặc webcam USB.
- Microphone tích hợp, headset hoặc microphone USB.
- Nhiều camera hoặc microphone trên cùng thiết bị.
- Thiết bị audio/video được browser và hệ điều hành nhận diện.

Ứng dụng thường xin quyền để:

- Gọi video hoặc hội nghị trực tuyến.
- Ghi âm, ghi hình theo yêu cầu rõ ràng của người dùng.
- Nhận dạng giọng nói hoặc xử lý media tại thiết bị.
- Chia sẻ luồng camera với RTCPeerConnection trong WebRTC.

### Quyền media không phải quyền đăng nhập

Browser permission trả lời câu hỏi: document có được phép lấy media từ thiết bị hay không?

Nó không xác định người dùng đã đăng nhập, có quyền tham gia phòng họp, có quyền ghi lại cuộc gọi hay có quyền gửi stream cho người khác. Những quyết định nghiệp vụ đó thuộc backend và ứng dụng.

Ví dụ, browser có thể cho phép camera nhưng server vẫn phải từ chối user không có quyền vào phòng họp. Ngược lại, user có tài khoản hợp lệ vẫn không thể sử dụng camera nếu người dùng hoặc browser từ chối permission.

### Ba lớp cần đồng thời cho phép

    Document gọi getUserMedia()
              |
              v
    Browser có hỗ trợ và secure context hợp lệ?
              |
              v
    Permissions Policy cho phép feature?
              |
              v
    Browser/user permission cho phép?
              |
              v
    Thiết bị khả dụng và constraints đáp ứng?
              |
              v
    MediaStream được trả về

Các bước có thể được kiểm tra theo thứ tự khác nhau tùy browser, nhưng kết quả cuối cùng phải đáp ứng mọi điều kiện liên quan. Không có một lớp nào tự thay thế các lớp còn lại.

## 2. Secure context: vì sao cần HTTPS?

MediaDevices.getUserMedia() chỉ khả dụng trong secure context theo quy tắc của browser. Production nên chạy qua HTTPS.

Các trường hợp thường gặp:

- HTTPS hợp lệ: secure context nếu certificate và môi trường được browser tin cậy.
- localhost: được browser coi là trustworthy origin cho phát triển trong nhiều trường hợp.
- HTTP trên hostname hoặc IP thông thường: không phải secure context và API có thể không khả dụng.
- Trang HTTPS nhúng tài nguyên hoặc frame không an toàn: có thể gặp mixed content hoặc giới hạn khác.

Kiểm tra:

    console.log(window.isSecureContext);
    console.log(navigator.mediaDevices);

Nếu isSecureContext là false hoặc navigator.mediaDevices không có, hãy kiểm tra URL, certificate, iframe và browser trước khi điều tra lỗi camera.

HTTPS chỉ bảo vệ kênh truyền và đáp ứng một điều kiện môi trường. HTTPS không tự cấp quyền camera, microphone hoặc chứng minh ứng dụng đáng tin cậy.

## 3. Xin quyền bằng getUserMedia()

getUserMedia() trả về Promise. Promise resolve với MediaStream khi browser cho phép và lấy được thiết bị phù hợp; Promise reject nếu request không thể hoàn tất.

Ví dụ xin cả camera và microphone:

    async function startCallPreview(videoElement) {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: true
      });

      videoElement.srcObject = stream;
      await videoElement.play();
      return stream;
    }

Trong HTML:

    <video id="local-preview" autoplay playsinline muted></video>

muted giúp preview local không phát lại âm thanh microphone vào loa, tránh feedback. playsinline hữu ích trên thiết bị di động để video hiển thị trong trang theo hành vi phù hợp.

### Chỉ xin đúng thiết bị cần dùng

Nếu chức năng chỉ cần microphone, đừng yêu cầu camera:

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: false
    });

Nếu chức năng chỉ cần camera:

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: true
    });

Xin quyền tối thiểu giúp người dùng hiểu mục đích và giảm dữ liệu nhạy cảm mà ứng dụng có thể thu thập.

### Browser có thể hiển thị prompt

Khi chưa có quyết định quyền phù hợp, browser thường hiển thị prompt để người dùng cho phép hoặc từ chối. Cách lưu quyết định khác nhau theo browser, hệ điều hành, chế độ riêng tư và cài đặt site.

Không giả định:

- Permission luôn được lưu vĩnh viễn.
- Mọi browser đều có cùng giao diện prompt.
- Người dùng từ chối một lần thì trạng thái luôn là denied ở mọi browser.
- HTTPS đồng nghĩa prompt sẽ tự động được chấp nhận.

Người dùng có thể thay đổi quyền trong site settings hoặc cài đặt hệ điều hành. Ứng dụng phải xử lý trường hợp quyền bị thu hồi sau khi đã hoạt động.

## 4. Constraints: yêu cầu media phù hợp

Tham số constraints mô tả loại track và đặc điểm media mà ứng dụng mong muốn.

Ví dụ:

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true
      },
      video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
        frameRate: { ideal: 30, max: 30 }
      }
    });

### Boolean constraints

- audio: true yêu cầu một audio track phù hợp.
- video: true yêu cầu một video track phù hợp.
- audio: false hoặc video: false nghĩa là không yêu cầu loại track đó.

### ideal, min, max và exact

| Constraint | Ý nghĩa |
| --- | --- |
| ideal | Giá trị ưu tiên; browser có thể chọn giá trị gần nhất |
| min | Giá trị thấp nhất được chấp nhận |
| max | Giá trị cao nhất được chấp nhận |
| exact | Giá trị bắt buộc; không đáp ứng thì request thất bại |

Ví dụ:

    video: {
      width: { ideal: 1280 },
      height: { ideal: 720 }
    }

Đây là gợi ý. Browser có thể chọn độ phân giải thấp hơn theo khả năng thiết bị.

Ví dụ yêu cầu bắt buộc:

    video: {
      width: { exact: 1920 },
      height: { exact: 1080 }
    }

Nếu không có thiết bị đáp ứng, request có thể reject với OverconstrainedError. Chỉ dùng exact khi nghiệp vụ thực sự cần giá trị đó.

### Chọn camera trước/sau

Trên thiết bị có camera trước/sau:

    const stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: { ideal: "environment" }
      },
      audio: false
    });

Giá trị thường gặp:

- user: camera hướng về người dùng.
- environment: camera hướng ra môi trường.

Browser và thiết bị có thể hỗ trợ khác nhau. Dùng ideal nếu có thể fallback.

### Chọn thiết bị bằng deviceId

Sau khi có quyền hoặc khi browser cho phép hiển thị thông tin thiết bị, ứng dụng có thể dùng deviceId để chọn nguồn cụ thể:

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        deviceId: { ideal: selectedMicrophoneId }
      },
      video: false
    });

Không coi deviceId là định danh thiết bị bền vững hoặc bí mật. Browser có thể thay đổi hoặc làm mờ định danh theo origin, profile, quyền và chính sách privacy. Không dùng deviceId làm fingerprint người dùng.

## 5. Các lỗi thường gặp khi xin quyền

Promise của getUserMedia() có thể reject với nhiều loại lỗi. Không hiển thị mọi lỗi thành một thông báo chung “camera không hoạt động”.

| Error name | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| NotAllowedError | Người dùng từ chối, browser/site policy chặn, Permissions Policy không cho phép hoặc môi trường không đáp ứng điều kiện | Kiểm tra permission, secure context, iframe và policy |
| NotFoundError | Không có thiết bị phù hợp với loại track được yêu cầu | Cho người dùng chọn thiết bị khác hoặc thông báo thiết bị chưa kết nối |
| NotReadableError | Thiết bị có nhưng OS, driver hoặc browser không thể đọc; có thể đang bị ứng dụng khác giữ | Đóng ứng dụng đang dùng thiết bị, kiểm tra OS và thử lại |
| OverconstrainedError | Không có thiết bị đáp ứng constraint bắt buộc | Nới exact/min/max, dùng ideal hoặc fallback |
| AbortError | Thiết bị hoặc browser không thể hoàn tất capture vì lỗi khác | Cho phép thử lại sau khi kiểm tra thiết bị |
| InvalidStateError | Document chưa ở trạng thái active phù hợp | Gọi từ document đang hoạt động |
| TypeError | Constraints không hợp lệ hoặc API không khả dụng trong môi trường hiện tại | Kiểm tra tham số và secure context |

### Xử lý lỗi có ngữ cảnh

    async function requestCameraAndMic() {
      try {
        return await navigator.mediaDevices.getUserMedia({
          audio: true,
          video: true
        });
      } catch (error) {
        switch (error.name) {
          case "NotAllowedError":
            showMessage("Quyền camera hoặc microphone chưa được cấp. Hãy kiểm tra quyền của trang.");
            break;
          case "NotFoundError":
            showMessage("Không tìm thấy camera hoặc microphone phù hợp.");
            break;
          case "NotReadableError":
            showMessage("Không thể mở thiết bị. Hãy kiểm tra ứng dụng khác hoặc cài đặt thiết bị.");
            break;
          case "OverconstrainedError":
            showMessage("Thiết bị không đáp ứng cấu hình media. Hãy thử cấu hình thấp hơn.");
            break;
          default:
            showMessage("Không thể khởi động media. Hãy thử lại sau.");
        }

        reportMediaError(error.name);
        return null;
      }
    }

Không gửi stack trace, thông tin thiết bị hoặc nội dung nhạy cảm lên telemetry. Chỉ ghi mã lỗi và ngữ cảnh tối thiểu cần thiết để hỗ trợ.

### Prompt không được trả lời ngay

Người dùng có thể để prompt ở trạng thái chờ. Promise getUserMedia() có thể vẫn pending trong thời gian dài; không phải lúc nào cũng reject khi người dùng chưa chọn.

Giao diện cần có trạng thái “Đang chờ quyền truy cập” và hướng dẫn người dùng quay lại prompt. Nếu người dùng bấm hủy ở ứng dụng, có thể bỏ qua kết quả về mặt UI, nhưng browser prompt không nhất thiết bị đóng bằng cách đó.

## 6. Permissions API và trạng thái quyền

Permissions API cho phép hỏi trạng thái một số quyền mà browser hỗ trợ:

    async function readCameraPermission() {
      try {
        const result = await navigator.permissions.query({
          name: "camera"
        });
        return result.state;
      } catch {
        return "unsupported";
      }
    }

Các trạng thái phổ biến:

| State | Ý nghĩa |
| --- | --- |
| granted | Browser báo quyền đã được cấp trong ngữ cảnh hiện tại |
| prompt | Browser có thể cần hỏi người dùng khi ứng dụng yêu cầu |
| denied | Quyền bị từ chối hoặc bị policy/cài đặt chặn |

### Permissions API không tự xin quyền

query() chỉ đọc trạng thái mà browser cung cấp. Nó không hiển thị prompt và không cấp quyền.

Hỗ trợ query camera/microphone và cách browser báo trạng thái có thể khác nhau. Một số browser có thể reject với TypeError hoặc không hỗ trợ descriptor tương ứng. Luôn có fallback và xử lý lỗi.

### Theo dõi thay đổi trạng thái

Nếu browser trả về PermissionStatus có hỗ trợ change event:

    const status = await navigator.permissions.query({
      name: "camera"
    });

    status.addEventListener("change", () => {
      console.log("Camera permission:", status.state);
    });

Không dựa duy nhất vào event này để quản lý stream. Việc người dùng thu hồi quyền, rút thiết bị hoặc OS thay đổi trạng thái có thể được phản ánh qua track event và lỗi thiết bị khác nhau. Hãy xử lý đồng thời vòng đời track và permission.

## 7. Origin và quyền media

Quyền media được gắn với ngữ cảnh website theo cách browser quản lý. Origin là bộ ba scheme, host và port.

Ví dụ:

    https://app.example.test
    https://admin.example.test
    http://app.example.test

Ba URL này khác origin do host hoặc scheme khác nhau. Không suy luận rằng subdomain cùng domain gốc tự chia sẻ quyền camera/microphone.

Browser có thể cung cấp giao diện quản lý quyền theo site hoặc origin; chi tiết lưu trữ permission và việc gộp theo site khác nhau giữa browser. Ứng dụng không nên dựa vào quyền đã cấp cho một origin khác.

### Quyền media không phải CORS

getUserMedia() không phải request Fetch/XHR đọc response từ server khác. CORS không cấp hoặc từ chối quyền camera/microphone.

Một trang có thể được phép truy cập camera nhưng không được phép đọc API cross-origin. Ngược lại, API có CORS hợp lệ không có nghĩa trang được phép truy cập camera.

### Quyền media không phải cookie/session

Cookie xác định session với server. Media permission do browser quản lý cho document. Logout khỏi backend không nhất thiết tự dừng MediaStream; ứng dụng phải chủ động dừng track và cập nhật UI.

## 8. Permissions Policy: giới hạn camera và microphone

Permissions Policy cho phép website kiểm soát feature browser mà document và iframe có thể sử dụng.

Ví dụ website không cần camera/microphone:

    Permissions-Policy: camera=(), microphone=()

Nếu website có một dịch vụ họp ở origin riêng:

    Permissions-Policy: camera=(self "https://meet.example.test"), microphone=(self "https://meet.example.test")

Trang host nhúng:

    <iframe
      src="https://meet.example.test/room"
      title="Phòng họp"
      allow="camera; microphone">
    </iframe>

### Hai lớp phải cùng cho phép

- Header Permissions-Policy của ancestor phải cho phép origin được delegate.
- Thuộc tính allow trên iframe phải cấp feature cần thiết cho frame.
- Mọi ancestor liên quan trong cây iframe không được chặn feature.
- Browser vẫn áp dụng permission prompt, secure context và điều kiện thiết bị.

Nếu parent chặn camera bằng camera=(), iframe con không thể mở lại bằng allow="camera".

### Default allowlist

Camera và microphone có default allowlist riêng theo đặc tả và browser; thường là self. Không dựa vào mặc định cho hệ thống production. Khai báo rõ feature và origin cần dùng, rồi kiểm tra browser mục tiêu.

### Không mở quyền rộng cho mọi frame

Tránh:

    Permissions-Policy: camera=*, microphone=*

Wildcard có thể mở rộng khả năng sử dụng thiết bị cho nhiều browsing context không cần thiết. Chỉ delegate cho origin đã xác minh và iframe có chức năng thực sự cần capture.

## 9. iframe, sandbox và media permission

Một ứng dụng có thể nhúng widget họp hoặc nội dung bên thứ ba trong iframe. Việc nhúng làm tăng số origin có thể yêu cầu quyền thiết bị.

Ví dụ:

    <iframe
      src="https://meet.example.test/embed"
      title="Cuộc họp"
      allow="camera; microphone">
    </iframe>

Khi dùng nested iframe, mỗi tầng cần delegate feature theo policy hiệu lực. Một ancestor chặn feature sẽ giới hạn các descendant.

### sandbox không tự cấp media permission

Thuộc tính sandbox giới hạn hành vi của iframe. Nó không tự cấp camera hoặc microphone. Cần đánh giá các token sandbox thực sự cần thiết và tương tác với origin của frame.

Không thêm allow-same-origin hoặc allow-scripts một cách máy móc chỉ để “sửa” lỗi media. Các token đó thay đổi ranh giới bảo mật của iframe và cần được đánh giá theo nội dung được nhúng.

### Ưu tiên top-level flow cho thao tác nhạy cảm

Nếu browser hoặc nền tảng có giới hạn đối với nested browsing context, hãy thiết kế luồng để người dùng mở trải nghiệm capture trong top-level app hoặc một frame được kiểm soát rõ ràng. Không tìm cách lách prompt hoặc policy bằng cách đổi iframe liên tục.

## 10. enumerateDevices(): liệt kê thiết bị

MediaDevices.enumerateDevices() trả danh sách thiết bị media browser cho phép trang nhìn thấy:

    const devices = await navigator.mediaDevices.enumerateDevices();

    for (const device of devices) {
      console.log(device.kind, device.label);
    }

Các kind thường gặp:

- audioinput: microphone.
- audiooutput: thiết bị phát âm thanh.
- videoinput: camera.

### Label có thể bị ẩn trước khi cấp quyền

Để hạn chế fingerprinting, browser có thể trả label rỗng hoặc chỉ hiển thị một phần thông tin thiết bị trước khi user cấp quyền. Danh sách thiết bị cũng có thể bị giới hạn bởi Permissions Policy.

Sau khi người dùng cấp quyền, browser có thể cung cấp thêm label và deviceId. Tuy vậy, không nên thu thập hoặc gửi danh sách thiết bị về server nếu không cần cho chức năng.

### devicechange

Thiết bị có thể được cắm/rút trong lúc ứng dụng đang chạy:

    navigator.mediaDevices.addEventListener("devicechange", async () => {
      const devices = await navigator.mediaDevices.enumerateDevices();
      refreshDevicePicker(devices);
    });

Hỗ trợ devicechange khác nhau giữa browser và thiết bị. Ứng dụng nên có fallback để người dùng bấm làm mới danh sách thiết bị.

Không tự động mở camera mới chỉ vì thiết bị xuất hiện. Hãy để người dùng chọn hoặc xác nhận khi thay đổi nguồn capture.

## 11. Vòng đời MediaStream và MediaStreamTrack

getUserMedia() trả về MediaStream chứa một hoặc nhiều track:

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: true
    });

Lấy track:

    const audioTracks = stream.getAudioTracks();
    const videoTracks = stream.getVideoTracks();
    const allTracks = stream.getTracks();

### Dừng track khi không còn cần

Khi kết thúc preview hoặc cuộc gọi, dừng toàn bộ track:

    function stopStream(stream) {
      for (const track of stream.getTracks()) {
        track.stop();
      }
    }

Dừng track là cách rõ ràng để kết thúc việc capture do ứng dụng khởi tạo. Chỉ gỡ stream khỏi video.srcObject không bảo đảm thiết bị đã ngừng capture.

### enabled=false khác stop()

- track.enabled = false tạm thời tắt dữ liệu track ở mức ứng dụng; track vẫn tồn tại và có thể tiếp tục giữ tài nguyên capture.
- track.stop() kết thúc track và giải phóng việc sử dụng nguồn capture khi không còn track khác dùng chung nguồn.

Nếu người dùng bấm “Tắt camera”, UI có thể đặt enabled=false để tạm dừng gửi hình. Nếu kết thúc cuộc gọi hoặc không còn cần thiết bị, hãy stop track.

### ended event

Track có thể kết thúc khi thiết bị bị rút, browser thu hồi quyền hoặc nguồn capture không còn khả dụng:

    for (const track of stream.getTracks()) {
      track.addEventListener("ended", () => {
        updateMediaStatus("ended");
      });
    }

Lưu ý: gọi track.stop() trực tiếp không phát ended event theo cách giống việc nguồn kết thúc từ bên ngoài. Nếu code tự stop, hãy cập nhật state/UI ngay trong luồng code đó.

### Logout và rời phòng

Khi user logout hoặc rời phòng:

1. Ngừng gửi track qua RTCPeerConnection.
2. Gỡ sender/track khỏi peer connection theo logic cuộc gọi.
3. Dừng local MediaStreamTrack.
4. Xóa stream khỏi preview element.
5. Đóng peer connection nếu cuộc gọi kết thúc.
6. Xóa trạng thái UI và dữ liệu tạm liên quan.

Ví dụ:

    function leaveCall(stream, videoElement, peerConnection) {
      if (peerConnection) {
        peerConnection.close();
      }

      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }

      if (videoElement) {
        videoElement.srcObject = null;
      }
    }

Backend cũng cần kết thúc session/phòng họp. Dừng track ở browser không tự xóa bản ghi hoặc dữ liệu đã gửi lên server.

## 12. Camera/microphone khác screen capture

Chia sẻ màn hình dùng API riêng:

    const displayStream =
      await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: false
      });

getDisplayMedia() không dùng chung permission camera/microphone. Browser yêu cầu người dùng chọn cửa sổ, tab hoặc màn hình theo giao diện riêng. Người dùng cần chủ động lựa chọn nguồn chia sẻ.

### Đặc điểm quan trọng của getDisplayMedia()

- Chỉ chạy trong secure context.
- Thường cần transient user activation, ví dụ click nút “Chia sẻ màn hình”.
- Browser hiển thị UI chọn nguồn; ứng dụng không được tự chọn màn hình của người dùng thay họ.
- Không nên lưu một quyết định cho phép rồi tự động capture màn hình ở lần sau.
- User có thể dừng chia sẻ qua browser UI; track có thể phát ended.
- Constraint không được dùng để ép browser bỏ qua lựa chọn của người dùng.

### Ví dụ bắt đầu screen share từ thao tác click

    shareButton.addEventListener("click", async () => {
      try {
        const stream = await navigator.mediaDevices.getDisplayMedia({
          video: true,
          audio: false
        });

        const [track] = stream.getVideoTracks();
        track.addEventListener("ended", () => {
          stopDisplayStream(stream);
          updateShareButton(false);
        });

        startSendingScreen(stream);
        updateShareButton(true);
      } catch (error) {
        handleDisplayCaptureError(error);
      }
    });

### Không nhầm quyền camera với quyền màn hình

Người dùng cho phép camera không có nghĩa ứng dụng được chia sẻ desktop. Người dùng cho phép microphone không có nghĩa ứng dụng được thu âm thanh hệ thống. Mỗi luồng capture phải được giải thích, xin quyền và dừng riêng.

## 13. Rủi ro XSS và script bên thứ ba

Nếu attacker thực thi JavaScript trong origin của ứng dụng, script đó có thể gọi getUserMedia() trong phạm vi policy và permission hiện có. Nếu người dùng đã cấp quyền cho origin, XSS có thể lợi dụng quyền đó để lấy stream hoặc thao tác media.

Ví dụ rủi ro:

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: true
    });

Đoạn code này hợp lệ với trang được phép và có quyền. Nếu cùng code được chạy bởi XSS, browser không tự hiểu rằng mục đích của script là độc hại chỉ vì nó được chèn vào trang.

### Phòng vệ nhiều lớp

- Ngăn XSS bằng output encoding theo context.
- Tránh innerHTML với dữ liệu không tin cậy; ưu tiên textContent.
- Dùng CSP nonce/hash và hạn chế script bên thứ ba.
- Dùng Trusted Types cho DOM sink phù hợp.
- Kiểm soát dependency và quyền thực thi script.
- Giới hạn camera/microphone qua Permissions Policy ở trang không cần.
- Không delegate media permission cho iframe không tin cậy.
- Hiển thị trạng thái camera/microphone đang bật rõ ràng.
- Dừng track khi rời luồng nghiệp vụ.

### CSP không thay media permission

CSP connect-src kiểm soát kết nối mạng như Fetch, XHR và WebSocket. Nó không phải directive cấp hoặc thu hồi camera/microphone.

Permissions Policy có thể chặn feature ở document/iframe, còn CSP giúp hạn chế script và kết nối. Cả hai bổ sung cho nhau.

### Không tin iframe chỉ vì cùng công ty

Subdomain hoặc ứng dụng đối tác có thể có mã nguồn, dependency và đội vận hành khác nhau. Chỉ delegate camera/microphone cho origin thực sự cần, đã được xác minh và có hợp đồng quyền riêng tư phù hợp.

## 14. Quyền riêng tư và trải nghiệm người dùng

Camera và microphone có thể thu dữ liệu nhạy cảm. Giao diện cần giúp người dùng hiểu rõ điều gì đang diễn ra.

Nên:

- Giải thích vì sao cần camera/microphone trước khi gọi API.
- Chỉ xin quyền khi người dùng bắt đầu chức năng liên quan.
- Hiển thị trạng thái đang dùng camera/microphone.
- Có nút tắt camera, tắt microphone và kết thúc capture.
- Hiển thị nguồn thiết bị đang dùng nếu có thể.
- Cho phép đổi thiết bị một cách rõ ràng.
- Dừng track khi rời phòng hoặc logout.
- Thông báo khi browser/OS thu hồi quyền hoặc thiết bị bị ngắt.
- Không ghi âm/ghi hình ngầm hoặc tiếp tục capture ngoài mục đích đã thông báo.

Không dùng prompt liên tục để gây áp lực khi người dùng từ chối. Hướng dẫn người dùng mở site settings nếu họ muốn thay đổi lựa chọn.

### Browser indicator và OS indicator

Browser thường hiển thị chỉ báo khi camera/microphone đang được sử dụng; hệ điều hành hiện đại cũng có thể có indicator riêng. Đây là tín hiệu quan trọng nhưng không thay thế UI trung thực của ứng dụng.

Ứng dụng không nên che, giả mạo hoặc gây nhầm lẫn với indicator của browser/OS.

### Dữ liệu media đi đâu?

Quyền capture chỉ cho phép trang nhận stream. Sau đó ứng dụng có thể:

- Hiển thị preview local.
- Gửi track qua RTCPeerConnection tới peer.
- Ghi lại bằng MediaRecorder.
- Upload dữ liệu lên server.

Đây là các hành động khác nhau. Cần thông báo và có cơ sở phù hợp cho việc ghi, truyền hoặc lưu trữ. Không suy luận rằng người dùng cho phép camera đồng nghĩa họ đã đồng ý ghi lại cuộc họp.

## 15. Xây dựng luồng xin quyền an toàn

Một luồng giao diện tốt nên có trạng thái rõ ràng:

1. Idle: chưa xin quyền.
2. Requesting: đang chờ browser/user.
3. Ready: đã có stream và preview.
4. Denied: người dùng/browser từ chối.
5. Unavailable: không có thiết bị hoặc thiết bị không hoạt động.
6. Stopped: capture đã dừng.

Ví dụ:

    let localStream = null;

    async function startPreview(videoElement) {
      if (!window.isSecureContext ||
          !navigator.mediaDevices?.getUserMedia) {
        showMediaError("Trình duyệt hoặc môi trường không hỗ trợ media capture.");
        return;
      }

      setMediaState("requesting");

      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
          video: true
        });

        localStream = stream;
        videoElement.srcObject = stream;
        await videoElement.play();

        for (const track of stream.getTracks()) {
          track.addEventListener("ended", () => {
            setMediaState("stopped");
          });
        }

        setMediaState("ready");
      } catch (error) {
        setMediaState("denied");
        showMediaError(mapMediaError(error));
      }
    }

    function stopPreview(videoElement) {
      if (localStream) {
        localStream.getTracks().forEach((track) => track.stop());
        localStream = null;
      }

      videoElement.srcObject = null;
      setMediaState("stopped");
    }

Ví dụ chỉ minh họa cấu trúc. Trong ứng dụng thực, quản lý nhiều lần start/stop, component unmount, request đang pending, track ended và lỗi play() để không rò rỉ stream.

### Tránh race khi người dùng bấm nhiều lần

Nếu người dùng bấm Start liên tục, có thể tạo nhiều request capture. Vô hiệu hóa nút trong trạng thái requesting hoặc quản lý request generation để chỉ giữ stream mới nhất. Nếu một Promise resolve sau khi UI đã rời trang, phải stop stream vừa nhận thay vì để camera tiếp tục chạy ngoài ý muốn.

## 16. Kiểm thử Media permission bằng DevTools

Thực hiện trên HTTPS local/staging với thiết bị test. Không ghi hoặc upload media thật trong lab.

### Bước 1 — Kiểm tra secure context

1. Mở trang qua HTTPS hoặc localhost.
2. Mở Console.
3. Kiểm tra window.isSecureContext.
4. Kiểm tra navigator.mediaDevices và getUserMedia.
5. Nếu API không có, kiểm tra HTTP, iframe và browser support.

### Bước 2 — Thử cấp và từ chối quyền

1. Mở chức năng preview.
2. Khi browser hiện prompt, thử Allow.
3. Dừng preview và xác nhận indicator camera/microphone tắt.
4. Reset quyền site trong cài đặt browser.
5. Thử lại và chọn Block.
6. Quan sát error name và UI fallback.

### Bước 3 — Kiểm tra Permissions Policy

Trong staging, phát:

    Permissions-Policy: camera=(), microphone=()

Thử gọi getUserMedia() và xác nhận feature bị chặn.

Sau đó thử policy chỉ cho phép origin họp và iframe allow tương ứng. Kiểm tra cả parent, child và nested iframe.

### Bước 4 — Kiểm tra thiết bị

1. Gọi enumerateDevices().
2. Quan sát label trước và sau khi cấp quyền.
3. Cắm/rút camera hoặc microphone test.
4. Quan sát devicechange nếu browser hỗ trợ.
5. Thử chọn deviceId không còn tồn tại và xử lý lỗi.

### Bước 5 — Kiểm tra vòng đời track

1. Xin camera/microphone.
2. Xác nhận track state và video preview.
3. Đặt enabled=false và quan sát trạng thái mute.
4. Gọi stop() và xác nhận capture kết thúc.
5. Thử rút thiết bị để quan sát ended.
6. Rời trang/logout và xác nhận ứng dụng dừng mọi track.

### Bước 6 — Kiểm tra screen capture riêng

1. Bấm nút Share screen trong staging.
2. Chọn một cửa sổ hoặc tab test.
3. Dừng chia sẻ từ browser UI.
4. Xác nhận track ended và ứng dụng cập nhật trạng thái.
5. Xác nhận quyền camera trước đó không tự động cấp screen capture.

### Ma trận kiểm thử

| Ca kiểm thử | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| HTTPS | Secure context hợp lệ | getUserMedia có thể được gọi |
| HTTP thông thường | Không phải secure context | API không khả dụng hoặc request bị từ chối |
| User cho phép | Camera/mic khả dụng | Promise resolve với MediaStream |
| User từ chối | Site permission bị Block | Promise reject, UI hướng dẫn rõ |
| Policy chặn | camera=() hoặc microphone=() | Feature tương ứng bị browser chặn |
| Iframe được delegate | Header và allow phù hợp | Frame có thể xin quyền nếu user/browser cho phép |
| Ancestor chặn | Parent policy deny | Child không thể mở lại feature |
| Không có thiết bị | Không có camera/mic phù hợp | NotFoundError hoặc lỗi tương ứng |
| Constraint exact không đáp ứng | Thiết bị không có độ phân giải yêu cầu | OverconstrainedError |
| Thiết bị bận | OS/browser không mở được thiết bị | NotReadableError hoặc lỗi phù hợp |
| Permission API không hỗ trợ | query descriptor bị từ chối | Fallback, không làm hỏng luồng capture |
| Device unplug | Rút thiết bị khi đang capture | Track có thể ended; UI xử lý |
| Stop track | Gọi track.stop() | Capture của track kết thúc |
| Logout | User rời ứng dụng | Track dừng, preview bị xóa |
| Screen capture | User click và chọn nguồn | getDisplayMedia trả stream theo lựa chọn |
| User dừng share | Dừng từ browser UI | Track ended và UI cập nhật |

## 17. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ HTTPS tự cấp camera permission | Request vẫn cần browser/user cho phép | Xem secure context là điều kiện, không phải consent |
| Xin cả audio và video dù chỉ cần một loại | Thu thập dữ liệu vượt mục đích | Chỉ xin track cần thiết |
| Nghĩ CORS quyết định camera permission | Nhầm hai cơ chế độc lập | Dùng Permissions Policy và browser permission |
| Chỉ kiểm tra permission lúc mở app | Quyền có thể bị thu hồi trong khi stream chạy | Theo dõi track và xử lý lỗi thiết bị |
| Dùng Permissions API để tự cấp quyền | query() không hiển thị prompt | Gọi getUserMedia sau hành động phù hợp của người dùng |
| Nghĩ iframe allow ghi đè policy parent | Ancestor deny vẫn có hiệu lực | Kiểm tra toàn bộ cây iframe |
| Mở camera cho mọi origin bằng wildcard | Mở rộng bề mặt truy cập thiết bị | Exact allowlist và delegate tối thiểu |
| Dùng deviceId làm định danh người dùng | Tăng rủi ro fingerprinting | Không dùng deviceId cho nhận dạng |
| Gỡ srcObject rồi cho rằng camera đã tắt | Track vẫn có thể capture | Gọi stop() trên mọi track |
| Chỉ đặt track.enabled=false khi kết thúc cuộc gọi | Thiết bị có thể vẫn bị giữ | Stop track khi không còn cần |
| Không xử lý Promise pending | UI có thể mắc ở trạng thái chờ | Hiển thị trạng thái và xử lý kết quả muộn |
| Nghĩ quyền camera bao gồm screen share | Mở nhầm phạm vi consent | Dùng getDisplayMedia và prompt riêng |
| Cho rằng logout tự dừng stream | Capture có thể tiếp tục sau logout | Dừng track và đóng peer connection |
| Tin XSS không thể gọi media vì cookie HttpOnly | XSS vẫn có thể gọi API trong origin được cấp quyền | Phòng XSS và giới hạn Permissions Policy |
| Ghi lại cuộc gọi chỉ vì user đã cho camera | Consent capture không đồng nghĩa consent recording | Thông báo và xin đồng ý riêng cho recording |

## 18. Câu hỏi củng cố

**Câu 1.** getUserMedia() dùng để làm gì?

**Giải đáp:** Yêu cầu browser cung cấp MediaStream từ camera và/hoặc microphone theo constraints, sau khi các điều kiện bảo mật và quyền người dùng được đáp ứng.

**Câu 2.** HTTPS có nghĩa người dùng đã cho phép camera không?

**Giải đáp:** Không. HTTPS tạo secure context và bảo vệ transport; browser vẫn áp dụng permission và policy.

**Câu 3.** Permissions API query camera có hiển thị prompt không?

**Giải đáp:** Không. query() chỉ đọc trạng thái browser hỗ trợ; getUserMedia() mới thực hiện yêu cầu capture và có thể kích hoạt prompt.

**Câu 4.** CORS có quyết định trang được dùng microphone không?

**Giải đáp:** Không. CORS kiểm soát việc đọc response mạng cross-origin; media permission do browser, Permissions Policy và user consent quyết định.

**Câu 5.** track.enabled=false khác track.stop() thế nào?

**Giải đáp:** enabled=false tạm tắt dữ liệu track nhưng track có thể vẫn giữ nguồn capture. stop() kết thúc track.

**Câu 6.** iframe có thể tự mở camera nếu parent đã chặn camera không?

**Giải đáp:** Không. Policy của ancestor là giới hạn; allow ở child không thể nới rộng quyền đã bị chặn.

**Câu 7.** getDisplayMedia() có dùng quyền camera đã cấp không?

**Giải đáp:** Không. Screen capture có API và luồng chọn nguồn riêng, thường yêu cầu user activation và prompt chọn nguồn.

**Câu 8.** Vì sao XSS nguy hiểm với media permission?

**Giải đáp:** Script chạy cùng origin có thể gọi API trong phạm vi quyền hiện có, đọc stream và gửi dữ liệu đi. HttpOnly cookie không ngăn hành vi đó.

## 19. Tổng kết

Media permission là cơ chế browser kiểm soát việc website truy cập camera và microphone. getUserMedia() chỉ hoạt động trong secure context và phải đáp ứng Permissions Policy, quyền người dùng cùng điều kiện thiết bị. Permissions API có thể cung cấp trạng thái khi được hỗ trợ nhưng không tự xin hoặc cấp quyền.

Hãy chỉ xin đúng loại media cần thiết, giải thích mục đích trước khi gọi API, xử lý các lỗi theo ngữ cảnh và quản lý MediaStreamTrack rõ ràng. Khi kết thúc preview, cuộc gọi hoặc logout, dừng mọi track và đóng kết nối liên quan. Với iframe, dùng Permissions-Policy và allow theo exact origin; frame con không thể mở lại feature mà ancestor đã chặn.

Screen capture qua getDisplayMedia() là luồng riêng, cần thao tác và lựa chọn của người dùng. Quyền capture không đồng nghĩa với quyền ghi lại hoặc chia sẻ dữ liệu. XSS vẫn có thể lợi dụng media permission đã cấp, vì vậy cần bảo vệ script, giảm third-party code, giới hạn iframe và hiển thị trạng thái capture minh bạch.

## Tài liệu tham khảo

1. [W3C — Media Capture and Streams](https://www.w3.org/TR/mediacapture-streams/): getUserMedia, MediaStream, MediaStreamTrack và constraints.
2. [MDN — MediaDevices.getUserMedia()](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia): secure context, permission và lỗi thường gặp.
3. [MDN — MediaDevices.enumerateDevices()](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/enumerateDevices): liệt kê thiết bị và giới hạn privacy.
4. [MDN — MediaStreamTrack](https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack): trạng thái, enabled, stop và ended.
5. [MDN — Permissions API](https://developer.mozilla.org/en-US/docs/Web/API/Permissions_API): query và theo dõi trạng thái quyền.
6. [MDN — MediaDevices.getDisplayMedia()](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia): screen capture và lựa chọn của người dùng.
7. [MDN — Permissions Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Permissions_Policy): giới hạn camera/microphone và iframe delegation.
