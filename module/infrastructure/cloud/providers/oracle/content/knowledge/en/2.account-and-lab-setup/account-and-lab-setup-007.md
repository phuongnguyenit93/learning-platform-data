# Using Cloud Shell and Code Editor

## Lesson Objectives

After this lesson, you will be able to open Cloud Shell and Code Editor from the OCI Console, run a read-only OCI query, create a learning workspace, and compile a small Java program. You will also be able to distinguish access permissions, network paths, session regions, and file storage locations.

This lesson belongs to the **Account and Lab Setup** chapter of the CLOUD_PROVIDERS_ORACLE module. The goal is a controlled operational environment to continue studying IAM, VCN, Compute, storage, and database services. The practice steps do not require creating VMs, buckets, or databases.

The Bash commands in this lesson run inside **OCI Cloud Shell**. Even if your personal machine runs Windows, you still enter those commands in the browser-based Cloud Shell terminal.

## 1. How Do Cloud Shell and Code Editor Work Together?

**Cloud Shell** is a terminal running in an OCI-managed environment accessed through the Console. **Code Editor** provides an editing UI for opening workspaces and working with files in your Cloud Shell session.

Work can be divided as follows:

| Tool | Appropriate tasks |
| --- | --- |
| OCI Console | Inspecting resources, verifying scope, and launching developer tools |
| Cloud Shell | Running CLI commands, inspecting the environment, compiling, and executing code |
| Code Editor | Creating, reading, editing, and saving source files in a workspace |
| Target services | Providing the resources accessed by your CLI commands or code |

The [Code Editor documentation](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/code_editor_intro.htm) describes direct integration with Cloud Shell and supported service workflows.

~~~mermaid
flowchart LR
    B["Browser / OCI Console"] --> E["Code Editor"]
    B --> T["Cloud Shell terminal"]
    E --> F["Files in the session workspace"]
    T --> F
    T -->|"CLI: authentication, IAM, and network"| O["OCI Services"]
~~~

In this lab, you edit a Java file in the editor and then use the terminal to compile that exact file. Opening the editor or terminal does not automatically deploy the program as a user-facing service.

## 2. Preparing Permissions and Practice Scope

You need to sign into the right tenancy using an assigned account with permission to use Cloud Shell. A sample policy for a group in an identity domain is:

~~~text
Allow group <DOMAIN_NAME>/<GROUP_NAME> to use cloud-shell in tenancy
~~~

An administrator replaces the placeholders with real names and configures the policy in the right scope. The Cloud Shell policy is tenancy-scoped; see [Cloud Shell — Required IAM Policy](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/cloudshellintro.htm#Required_IAM_Policy).

Code Editor uses the Cloud Shell access policy. If you use service plugins, you also need permissions for that service and compartment visibility per the Code Editor documentation.

Distinguish three conditions:

| Condition | Example question |
| --- | --- |
| Permission to open the tool | Is the account allowed to use Cloud Shell? |
| Permission to perform an action | Is the account allowed to list Compute instances in the lab compartment? |
| Network path | Can the session reach the target endpoint? |

For example, a learner who can open Cloud Shell but is not permitted to view instances will still receive an authorization error when calling the Compute API. Conversely, having sufficient IAM permissions does not guarantee network connectivity to a private endpoint.

In this lesson, querying Compute is optional if the learner has already been granted read permission. There is no need to grant tenancy-wide administrator permissions just to practice the editor and Java.

## 3. Opening Cloud Shell and Verifying the Environment

### 3.1. Start a Session

1. Sign into the OCI Console with your learning account.
2. Check the active tenancy and selected region.
3. For your first practice session, choose your tenancy's home region and inspect the session launch mode.
4. Click the **Cloud Shell/Code Editor** icon in the top header bar.
5. Select **Cloud Shell** and wait for the terminal to become ready.

Steps for opening the tool are shown in [Using Cloud Shell](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/devcloudshellgettingstarted.htm).

Cloud Shell provides an OCI CLI pre-authenticated for the session. Therefore, this lab does not require creating extra API keys or re-running the local workstation CLI setup workflow.

### 3.2. Inspect Tools

Enter each command in the terminal:

~~~bash
pwd
whoami
uname -m
oci --version
java -version
javac -version
~~~

Meaning of the outputs:

| Command | Information to observe |
| --- | --- |
| pwd | Current working directory |
| whoami | OS username inside the shell environment |
| uname -m | Runtime environment architecture |
| oci --version | Available CLI version |
| java -version | Active Java runtime |
| javac -version | Active Java compiler |

The name returned by whoami is the OS username; it is not full proof of all IAM permissions held by the OCI account.

Output does not need to match a tutorial screenshot character-for-character. Tool versions can change; verify that the commands exist and suit the code you plan to run.

### 3.3. Check Java Runtimes When Needed

You can list supported Java runtimes:

~~~bash
csruntimectl java list
~~~

If you need to switch runtimes, select an actual alias from the list and read the help first:

~~~bash
csruntimectl help
~~~

After switching, re-run java -version and javac -version. Do not pick an alias solely because it appeared in an older article.

Runtime management is described in the **Managing Language Runtimes** section of the Using Cloud Shell documentation.

## 4. Distinguishing Session Region and CLI Target Region

There are two locations to observe:

| Concept | Meaning |
| --- | --- |
| Cloud Shell session region | Where the shell environment and session workspace run |
| OCI CLI target region | The region targeted by an OCI command |

According to Cloud Shell documentation, sessions default to the home region; regional launch allows starting a session in a selected region. The CLI's default target region is taken from the Console selection when the session started and can differ from the session region.

Switching regions in the Console while a session is open does not automatically move the running shell environment. For a command requiring explicit scope, pass --region.

### 4.1. Set Scope for the Lab

In the terminal, set variables specifically for this lesson:

~~~bash
lab_region='<ACTUAL_REGION_ID>'
lab_compartment_ocid='<LAB_COMPARTMENT_OCID>'
~~~

Replace placeholders only with values issued for your learning environment. Do not use a production compartment for testing.

Example using the variables:

~~~bash
oci os ns get --region "$lab_region"
~~~

Specifying a region does not automatically create network connectivity to that region. If the network mode only allows reaching services within the session region, select an appropriate session or network mode instead.

### 4.2. Workspaces in the Home Region vs. Outside the Home Region

The [Working with Workspaces](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/code_editor_using_workspaces.htm) documentation notes that session files outside the home region are ephemeral. Back them up before the session environment is terminated.

For your first lesson, using the home region simplifies continuing work across sessions. Even so, important study files still need an independent backup.

Do not confuse restorable editor UI state with a guarantee that all files in every region are preserved.

## 5. Running Your First OCI Query

### 5.1. Retrieve the Object Storage Namespace

Run:

~~~bash
oci os ns get --region "$lab_region"
~~~

Illustrative output format:

~~~json
{
  "data": "<object-storage-namespace>"
}
~~~

The namespace is your tenancy's Object Storage namespace identifier, not a bucket name and not a compartment OCID. Refer to [OCI CLI — os ns get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/ns/get.html).

You can extract only the value:

~~~bash
oci os ns get --region "$lab_region" --query data --raw-output
~~~

In this command:

- --region selects the target region.
- --query data extracts the data field from the response.
- --raw-output prints the plain string instead of a quoted JSON string.

Retrieving the namespace does not create a bucket or upload data to the service.

### 5.2. List Instances in the Lab Compartment, If Permitted

~~~bash
oci compute instance list \
  --compartment-id "$lab_compartment_ocid" \
  --region "$lab_region" \
  --all \
  --query 'data[].{name:"display-name",state:"lifecycle-state"}' \
  --output table
~~~

The trailing backslash is Bash line continuation. Do not add trailing spaces or characters after the backslash.

The [OCI CLI — compute instance list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/compute/instance/list.html) documentation describes compartment parameters, filters, and pagination. --all retrieves all pages of results; the --query expression selects name and state for a readable table.

An empty result only indicates that the command returned no instances in the queried scope. Cross-check region, compartment, and filters in the Console before concluding a resource does not exist.

If you receive a permission error, record the action, scope, and error code for your administrator to inspect. The Java practice below does not depend on listing instances successfully.

## 6. Creating a Workspace and Opening It in Code Editor

### 6.1. Create a Learning Directory in Cloud Shell

~~~bash
mkdir -p "$HOME/oci-labs/cloud-shell-editor"
cd "$HOME/oci-labs/cloud-shell-editor"
pwd
~~~

The HOME variable is used as provided by the environment; do not reassign it. Save the absolute path returned by pwd so you open the exact directory in the editor.

Expected structure:

~~~text
oci-labs/
└── cloud-shell-editor/
    ├── HelloOci.java
    └── out/
~~~

These are files you create inside your Cloud Shell environment, not Compute or database resources in the tenancy.

### 6.2. Open the Editor

From the Cloud Shell/Code Editor icon in the Console, select **Code Editor**. If layout options exist, you can place the editor and terminal side by side or switch tabs.

According to [Launching Code Editor](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/code_editor_using_launching_code_editor.htm), Code Editor uses Cloud Shell's session region and has specific browser window requirements. Practice in a standard browser window.

Use the editor's open-folder feature and choose the absolute path retrieved from pwd. Menu names may vary across UI updates; the expected result is the left file tree showing the `cloud-shell-editor` folder.

### 6.3. Open a Terminal in the Exact Directory

You can choose Terminal from the editor menu or right-click the folder and choose **Open In Terminal**. The latter opens a terminal with the selected folder as its working directory; see [Starting a Terminal Session](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/code_editor_using_starting_a_terminal_session.htm).

In the new terminal, run:

~~~bash
pwd
~~~

If the output differs from your lab directory, switch back to the lab path before compiling. Many "file not found" errors happen because the terminal is in a different directory than the one shown in the editor.

## 7. Writing and Running a Small Java Program

### 7.1. Create the File in the Editor

In the workspace, create **HelloOci.java** and enter:

~~~java
public class HelloOci {
    public static void main(String[] args) {
        String learner = args.length == 0 ? "learner" : args[0];
        System.out.println("Hello OCI, " + learner + "!");
    }
}
~~~

Save the file and check the folder tree. The filename must match the public class name exactly, including uppercase and lowercase letters.

This program only prints a message. It makes no OCI API calls, needs no OCI SDK, and contains no credentials.

### 7.2. Inspect the File from the Terminal

In the lab directory's terminal:

~~~bash
pwd
ls -l HelloOci.java
sed -n '1,20p' HelloOci.java
~~~

If your entered contents do not appear, check whether the file was saved and whether the editor opened the exact same workspace.

### 7.3. Compile and Run

~~~bash
mkdir -p out

if javac -d out HelloOci.java; then
    java -cp out HelloOci "OCI learner"
fi
~~~

Expected output:

~~~text
Hello OCI, OCI learner!
~~~

Explanation:

| Component | Role |
| --- | --- |
| javac | Compiles Java source code |
| -d out | Writes compiled class files into the out directory |
| java -cp out | Uses out as the classpath |
| HelloOci | Name of the class containing the main method |
| "OCI learner" | A string argument passed to the program |

The if block runs the program only when compilation succeeds. This prevents accidentally running a stale class file when newer code fails to compile.

### 7.4. Observe the Relationship Between Editor and Terminal

Change the message in the editor, save the file, then recompile and run again. Next, inspect:

~~~bash
ls -l HelloOci.java out/HelloOci.class
~~~

Observe three distinct states:

1. Unsaved buffer contents in the editor tab.
2. Saved file contents on disk.
3. Compiled class artifact produced by a successful build.

Saving a Java file does not automatically compile it. Compiling successfully does not automatically turn the program into a web application deployed on OCI.

### 7.5. Troubleshooting Errors

| Error or symptom | How to check |
| --- | --- |
| file not found | Run pwd and check the file path |
| Public class must reside in a file of the same name | Compare HelloOci against HelloOci.java |
| Syntax error | Check braces, semicolons, and quotes |
| Could not find or load main class | Check classpath, class name, and compilation output |
| Printed output stays stale | Save the file and recompile in the exact directory |
| UnsupportedClassVersionError | Compare the javac version that built the class with the running java version |

This exercise uses only the standard library and needs no external dependencies. If Java works here but another project fails to download libraries, check network access and that project's repository configuration.

## 8. Understanding Network Modes Before Calling Services

Cloud Shell supports different connectivity modes:

| Mode | Purpose |
| --- | --- |
| OCI Service Network | Reach OCI services in the session region within supported capabilities |
| Public Network | Connect to the Internet when permitted by policy |
| Private Network Access | Connect to a configured private network |

The [Cloud Shell Networking](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/cloudshellintro_topic-Cloud_Shell_Networking.htm) documentation describes these modes and required permissions. Public Network requires its own permission; Private Network requires selecting a network along with matching permission, subnet, and routing/security rules.

Do not treat being able to open the Console as proof that the terminal can reach every address.

### 8.1. Distinguish Three Traffic Paths

~~~text
Browser → OCI Console
Cloud Shell → OCI service management APIs
Cloud Shell → private endpoint of a VM or database
~~~

These three paths have different origins, identities, and network requirements.

For instance, a command listing database metadata might succeed because it calls management APIs. An SQL connection to that database can still fail due to network routing, TLS configuration, or database-level privileges.

Similarly, cloning a public repository requires an appropriate outbound Internet path. Failing to download code does not mean your account lost all OCI permissions.

### 8.2. Changing Regions Does Not Replace Network Configuration

The --region flag specifies the API endpoint target; it does not create routes, open network rules, or attach the session to a private subnet.

Before attempting to access private resources, identify the target service's endpoint, session region, network mode, and authentication method.

In this basic lab, you do not need to configure Private Network or grant extra Internet access to run the Java program above. Apply additional network configuration only when a subsequent lab explicitly requires it.

### 8.3. When Should You Check Public Network Policy?

If a practice goal genuinely requires downloading code or dependencies from the Internet, an administrator can evaluate Public Network permissions under tenancy policy.

Do not turn on extra permissions merely to make an arbitrary test command succeed. Define the download source, purpose, and required access scope first.

## 9. Saving Your Work and Continuing in a Future Session

### 9.1. Distinguish Types of State

| State type | Example | Action needed |
| --- | --- | --- |
| Unsaved editor buffer | Changes in an open tab | Save the file before leaving the session |
| Files in workspace | HelloOci.java | Verify region and retention policy |
| Terminal state | Working directory, Bash variables | Prepare steps to re-initialize in a new session |
| Running processes | A Java task | Do not rely on keeping the browser tab open forever |
| OCI resources | VMs or buckets created via API | Manage lifecycle independently of the terminal window |

Persisted files do not mean shell variables or running processes are restored as-is.

When returning to the lesson, you can start with:

~~~bash
cd "$HOME/oci-labs/cloud-shell-editor"
pwd
ls -l HelloOci.java
java -version
~~~

Then re-set the needed lab variables. Never place passwords or tokens in a setup script just for convenience when resuming a lesson.

### 9.2. Save a Copy of Your Source Code

A simple approach is downloading source files to your computer using Cloud Shell's Download feature. For multiple files, package only the lab folder:

~~~bash
tar -czf "$HOME/cloud-shell-editor-lab.tar.gz" \
  -C "$HOME/oci-labs" \
  cloud-shell-editor

tar -tzf "$HOME/cloud-shell-editor-lab.tar.gz"
~~~

The first command creates an archive in your session home directory; the second lists its contents to verify. Next, use the Download feature to transfer the archive to your local machine and confirm it downloaded properly.

Simply creating an archive inside the same environment does not produce an independent backup. For ephemeral sessions, complete copying the backup to durable storage before ending the session.

Scope archives by project. Avoid archiving your entire home directory indiscriminately, as that can bundle unrelated configs, keys, or data.

### 9.3. Backup Does Not Mean Automatic Synchronization

Oracle documents backing up and restoring home directories via Object Storage in the Using Cloud Shell guide. This lesson downloads lab code directly so it does not require creating an extra bucket.

If using a Git repository in another workflow, inspect contents before pushing to a shared location. Editor Git integration is a helper tool; saving files, committing revisions, and pushing to a remote server remain distinct actions.

Never commit secrets to source code assuming deleting them in a later commit removes all prior copies.

## 10. Usage Limits and Choosing the Right Environment

Cloud Shell serves interactive tasks and enforces session, storage, and usage limits; refer to Cloud Shell docs and [Limits by Service](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/default.htm).

Key decisions to remember:

| Need | Recommended environment |
| --- | --- |
| Learning CLI, editing scripts, running small programs | Cloud Shell and Code Editor |
| Keeping recoverable source code | Independent backup following project workflow |
| Running long or heavy workloads | Choose an appropriate execution environment |
| Serving APIs to users | Deploy to an application platform or resource built for that purpose |
| Using a dedicated database | Configure the corresponding service, connectivity, and data privileges |

Cloud Shell is provided free within applicable limits; resources you create or services you call remain subject to their own pricing policies.

Closing Cloud Shell does not clean up VMs, volumes, buckets, or databases created earlier. Cost management must follow your lab resource inventory.

The Java program in this lesson exits immediately after printing its output. In later lessons, pick execution targets based on runtime duration, load, storage, and availability goals rather than turning a learning terminal into a critical system component.

## 11. Protecting Identity and Data in the Lab Environment

Cloud Shell acts under the session's authenticated identity, so read OCI commands carefully before running them.

A good habit is checking:

- Does the command read or mutate resources?
- Do the region and compartment match the learning environment?
- Does the input contain secrets?
- Is the output safe to share in a report?
- Does the tool request extra permissions or connections this lesson does not need?

In the editor, distinguish **Save** from plugin actions like deploying, invoking a function, or running infrastructure jobs. Editing a config file and applying changes to a service are separate steps.

For example, [Editing a Configuration Using Code Editor](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/code-editor.htm) separates editing a Resource Manager configuration from plan and apply actions. When encountering a service action button, read its impact rather than assuming it is harmless just because it sits inside the editor.

For lab reports, record only tool versions, project paths, Java output, and query scope. Never copy tokens, private keys, or full auth environment dumps into documentation.

## 12. Troubleshooting Common Errors

| Symptom | First check | How to handle |
| --- | --- | --- |
| Cannot open Cloud Shell | Account, tool permissions, browser state | Check IAM and error details; do not grant yourself broad privileges |
| Editor behaves unstably | Browser window type and current session | Use a normal browser window per Code Editor guidance |
| Terminal opens but API denies access | Error code, identity, and command scope | Check permissions for the action and target resource |
| Cannot download code or dependencies | Network mode and destination | Confirm an appropriate network path before editing code |
| Cannot reach private database | Endpoint, session region, Private Network, and data privileges | Separate network failures from database auth failures |
| Newly created file missing | Workspace, current directory, account, and session region | Run pwd, check paths, and check backups |
| Java output stays unchanged | Saved file and latest build | Recompile the exact file before running |
| Command from guide throws syntax error | Shell and copy-pasted characters | Use Bash syntax in Cloud Shell; check line continuations |

Several cases warrant extra clarification:

### 12.1. Console Works but Terminal Cannot Connect

Cloud Shell opens a browser connection to its own backend service. Cloud Shell docs note WebSocket requirements; proxies or browser policies can interfere with opening sessions.

Record the exact error message and check with your environment administrator when needed. Being able to load a Console page does not prove every connection required by developer tools is permitted.

### 12.2. CLI Is Authenticated but Still Returns Errors

"Authenticated" answers which identity is active; "authorized" depends on IAM for each operation. Check the exact tenancy, compartment, region, and target resource.

If the session expires, save your work and start a new session via the Console. Avoid copying old session credentials into a separate file to keep them alive.

### 12.3. Workspace Missing in the Next Session

Double-check your previous session's account and region. Do not treat home directories in different regions as automatically synchronized storage.

If code you wanted to keep was inside a terminated ephemeral session, do not assume the service can recover it. Build the habit of downloading or backing up copies during practice.

### 12.4. Resource Missing Even Though Console Showed It

Compare Console filters against CLI flags. A command may be querying a different compartment or region, or applying an unsuitable filter.

Move on to resource-modifying commands only after understanding the query results. Never recreate a resource just because a list came back empty.

## 13. Ending the Lab Session

Before leaving the session, proceed in order:

1. Save all open modified files.
2. Verify HelloOci.java from the terminal.
3. Compile and run the program successfully.
4. Create and verify a backup copy of your lab code if you need to keep it.
5. Confirm the backup is stored in an independent location.
6. Stop any remaining interactive tasks.
7. Close or terminate the session using the tool's controls.

Within the scope of this lesson, the OCI queries create no new service resources. If you ran additional commands from another lesson in the same session, manage and verify any created resources per that lesson.

There is no need to run mass-delete commands or reset your entire home directory to finish this lesson. Small lab files may remain in your workspace for continued practice if allowed by retention policies.

## 14. Completion Criteria

You have completed this lesson when you can demonstrate:

| Outcome | Appropriate evidence |
| --- | --- |
| Environment opens | Cloud Shell and Code Editor work with your assigned account |
| Scope understood | Can explain session region, target region, and lab compartment |
| OCI CLI works | Retrieved namespace or clearly identified the missing prerequisite for the query |
| Workspace works | Editor and terminal read the exact same source file |
| Java runs | Output `Hello OCI, OCI learner!` appears after successful compilation |
| Data retention understood | Identified files to keep and where an independent copy is stored |
| Permission and network boundaries understood | Distinguished tool access permission from service permissions and network paths |
| Controlled shutdown | Saved work and know which resources persist beyond the session lifecycle |

Cloud Shell and Code Editor offer a convenient starting point for learning OCI. As you move on to VCN, Compute, storage, and databases, keep the same discipline: **verify scope, check permissions and networking, act with intent, inspect outputs, and save work you need to keep**.
