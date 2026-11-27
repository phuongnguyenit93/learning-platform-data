# Configuring Runtimes, Environment Variables, and Startup Commands

An application runs smoothly on a laptop, yet when deployed to **Azure App Service** it returns HTTP 500, 502, or an "Application Error" screen. Sometimes the cause is not the source code: the app may be running on the wrong Node.js/Python/.NET/Java version, missing environment variables, trying to bind an unexpected port, or executing a **startup command** pointing to a nonexistent file. Because App Service manages the operating system and much of the underlying infrastructure, understanding the boundary between **platform configuration** and **application configuration** is an essential operational skill.

This lesson belongs to the **Web Applications with App Service** chapter in the **CLOUD_PROVIDERS_AZURE** module. The module explores the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networking, compute, storage, and data—then deploying, monitoring, securing, and controlling the cost of an application architecture. Within it, App Service lets you run web apps and APIs under a PaaS model: you focus on application code and settings while the platform handles tasks such as host provisioning, deployment integration, and instance operations.

After this lesson, you will be able to:

- Distinguish between **App Service Plan**, **Web App**, **runtime stack**, **application settings**, and **startup command**.
- Choose the right runtime, version, operating system, and code-based vs. custom container model.
- Use environment variables to configure applications per environment without hard-coding values.
- Integrate **managed identity** and **Key Vault references** so passwords are never placed in source code.
- Understand default startup behavior and when to set a custom startup command for Node.js, Python, and other runtimes.
- Configure settings via Azure Portal/Azure CLI, verify results, deploy via slots, and troubleshoot startup errors.
- Design health checks, logging, security, rollbacks, and cost control around configuration changes.

## 1. How does App Service run applications?

**Azure App Service** is a managed hosting service for web applications, APIs, and supported application scenarios. There are two resources to distinguish:

| Component | Key decisions | Example |
|---|---|---|
| **App Service Plan** | Region, OS, compute size/capacity, tier, scaling capability, and infrastructure features | Linux plan, Basic SKU |
| **Web App (App Service app)** | Specific app, hostname, runtime stack, configuration, deployment, identity, slots, networking | api-orders-prod |

Multiple Web Apps can share a single App Service Plan when platform requirements are met; in that case they **share compute capacity and plan cost scope**. Changing a Web App's runtime configuration does not change the plan's size.

~~~text
Azure subscription
└── Resource group
    ├── App Service Plan (Linux / compute capacity)
    │   ├── Web App: orders-api
    │   │   ├── Runtime: Node.js (example)
    │   │   ├── App settings: APP_ENV, LOG_LEVEL, ...
    │   │   ├── Startup command: npm start
    │   │   └── Managed identity / Networking
    │   └── Web App: catalog-api
    │       └── Independent configuration
    └── Key Vault / Database / Application Insights
~~~

The **runtime stack** is the execution environment for your code: Node.js, Python, .NET, Java, PHP, or another option supported by App Service for the corresponding OS/tier. **Application settings** are name/value pairs supplied by the platform to the process; the **startup command** defines how to launch the app when the default mechanism is insufficient.

For an app to actually serve requests, all four elements must align: **the right deployed artifact → the right runtime and launch command → the right dependency configuration → listening for HTTP on the address/port expected by the platform**.

## 2. Choosing the deployment model: built-in runtime vs. custom container

App Service has three common models:

| Model | What you package | How the runtime is chosen | When suitable |
|---|---|---|---|
| **Code-based App Service** | Source code or language-specific build artifact | Select a supported built-in runtime stack and version | App uses standard runtimes and you want minimal container management |
| **Custom Linux container** | Container image and image registry configuration | Runtime lives inside the image; App Service manages running the container | Need custom system libraries, specialized runtime/entrypoint, or packaging |
| **Windows App Service** | Artifact compatible with Windows/IIS/supported runtimes | Select Windows stack; startup behavior differs from Linux | .NET/ASP.NET apps or Windows-specific requirements |

With **code-based Linux**, App Service selects the base image/runtime matching the chosen version, then launches your app via the default mechanism or your configured command. With a **custom container**, the Node/Python/Java version lives inside the **Docker image**; changing a code-based runtime stack field is not how you upgrade the runtime inside an image.

### Choose the operating system before choosing the version

- Confirm whether the application depends on Linux or Windows (native libraries, IIS, shell commands, file paths, filesystem case sensitivity).
- Verify framework versions, runtimes, and Azure App Service support status at deployment time.
- Check required features/tiers, such as deployment slots, Always On, VNet Integration, and scaling.
- Determine region, budget, compliance, and the ability to test in a slot or staging environment.
- Separate **runtime version** from **SDK/build tool version**: compiling successfully does not prove the artifact is compatible with the live runtime.

Do not assume every language and version is supported on every OS. Supported lists evolve over the service lifecycle; query currently available runtimes via the Portal or CLI instead of copying an old example.

## 3. Understanding runtime stack and version

In code-based Linux App Service, runtime information typically resides in the **linuxFxVersion** setting. Illustrative examples:

~~~text
NODE|22-lts
PYTHON|3.11
DOTNETCORE|8.0
~~~

These values only **illustrate the format**, not a guarantee that they are always enabled for your app/region. Choose the exact runtime string returned by the list command or Portal. On Windows, the properties controlling stack/version differ, and some runtimes follow distinct hosting models.

### Why does the runtime version matter?

A Node.js app using APIs introduced in a newer Node release may fail if App Service runs an older version. A Python app with dependencies supporting only a specific version range may fail to build or fail to import. A .NET app built targeting a newer runtime than the host provides may fail to start.

Control compatibility in three places:

1. **Source/dependency manifest:** `package.json`, `requirements.txt`/`pyproject.toml`, `.csproj`, or equivalent.
2. **Build pipeline:** SDK version and artifact packaging process.
3. **App Service runtime:** actual process runtime version.

Ideally, CI and staging use the same platform and version planned for production. When upgrading a runtime, test **startup, data connectivity, health endpoints, business flows, and observability** before shifting traffic.

## 4. Configuring the runtime in the Azure Portal

For an existing **code-based Web App**:

1. Open the [Azure Portal](https://portal.azure.com/) and select the right subscription and resource group.
2. Open the Web App and note its **App Service Plan**, **Operating System**, and app state.
3. Go to **Configuration** or **Settings > Configuration / General settings** depending on the UI.
4. Locate **Stack settings** (runtime stack/version) if the app supports editing it in the Portal.
5. Choose a supported runtime version for your language and OS; verify app compatibility.
6. Save changes and monitor the application process restart/recycle.
7. Check logs, the health endpoint, and critical business flows.

Do not change a production runtime directly just "to see if it fixes an error" without verifying artifact and dependency compatibility. For critical systems, use a **deployment slot** or staging environment with a rollback plan.

### When the desired runtime stack does not appear

You may have created a **custom container**, picked the wrong OS, selected a stack whose support status changed, or hit a policy/tier restriction. Check the Web App kind and Azure's published runtime list before deciding to recreate the resource.

## 5. Inspecting and changing the runtime with Azure CLI

These commands use **Bash** in Azure Cloud Shell or a Bash terminal with Azure CLI installed. Sign in, select your subscription, and list available runtimes:

~~~bash
az login
az account list --output table
az account set --subscription "<SUBSCRIPTION_ID>"

az webapp list-runtimes --os-type linux --output table
~~~

List Windows runtimes if you need to compare:

~~~bash
az webapp list-runtimes --os-type windows --output table
~~~

For an existing code-based Linux app:

~~~bash
RG="<RESOURCE_GROUP>"
APP="<WEB_APP_NAME>"

az webapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{name:name,kind:kind,state:state,host:defaultHostName}" \
  --output json

az webapp config show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{runtime:linuxFxVersion,startup:appCommandLine,alwaysOn:alwaysOn}" \
  --output json
~~~

Only after selecting a valid string from the runtime list should you update it:

~~~bash
RUNTIME="<SUPPORTED_LINUX_RUNTIME_VALUE>"

az webapp config set \
  --resource-group "$RG" \
  --name "$APP" \
  --linux-fx-version "$RUNTIME"
~~~

For example, **SUPPORTED_LINUX_RUNTIME_VALUE** might look like **NODE|22-lts** if supported by the app, region, and platform. An invalid value can prevent the app from booting. **Do not use this `linuxFxVersion` update command to change the runtime version inside a custom container image**.

The **show/list-runtimes** commands only display configuration or platform-published options; they do not prove deployed dependencies are compatible. After changing a runtime, test real requests and inspect logs.

## 6. Application settings are environment variables

In Azure App Service, **Application settings (App settings)** are **name=value** pairs managed at the Web App/slot level. In common App Service models, these values are injected into the application process as **environment variables** at startup.

Examples:

| Setting name | Example value | How the app uses it |
|---|---|---|
| **APP_ENV** | production | Selects business application profile |
| **LOG_LEVEL** | info | Controls log verbosity |
| **FEATURE_EXPORT_ENABLED** | false | Toggles a feature implemented in code |
| **API_BASE_URL** | https://api.example.test | Dependent service address |
| **DB_HOST** | db.example.internal | Allowed database hostname |

**APP_ENV** and **FEATURE_EXPORT_ENABLED** are simply custom variables defined by your application. Azure does not automatically interpret every custom setting. Only settings read by your code or the platform take effect.

### Reading variables by runtime

**Node.js:**

~~~javascript
const logLevel = process.env.LOG_LEVEL ?? "info";
const isProduction = process.env.APP_ENV === "production";
~~~

**Python:**

~~~python
import os

log_level = os.environ.get("LOG_LEVEL", "info")
is_production = os.environ.get("APP_ENV") == "production"
~~~

**.NET:**

~~~csharp
var logLevel = Environment.GetEnvironmentVariable("LOG_LEVEL") ?? "info";
~~~

**Java:**

~~~java
String logLevel = System.getenv().getOrDefault("LOG_LEVEL", "info");
~~~

In .NET, ASP.NET Core also uses configuration providers, and App Service settings are typically surfaced via the environment-variable provider. Hierarchical key mapping (such as **__** delimiters) depends on the framework and configuration provider precedence. Do not assume every framework reads app settings identically.

### Key points to remember

- App Service app settings usually **override or take precedence** over corresponding values in certain app config files, depending on framework precedence rules.
- Modifying App settings typically **triggers an app restart/recycle** so the process picks up new values; plan for production impact.
- On Windows, environment variable names may be treated case-insensitively; on Linux, **LOG_LEVEL** and **log_level** are distinct names.
- Environment values are strings. Code must parse booleans, integers, or JSON with explicit validation.
- Do not arbitrarily overwrite Azure- or runtime-managed variables such as **WEBSITE_***, **WEBSITES_***, or **PORT** without understanding their role and documentation.
- A **.env** file in source code is not handled identically by Azure across all frameworks. Manage production settings via App Service, managed identity, and an appropriate secret store.

## 7. Configuring App settings via Portal and CLI

### In the Portal

1. Open the Web App → **Environment variables** or **Configuration > Application settings** depending on the UI.
2. Add a setting, such as **LOG_LEVEL=info**.
3. Decide whether it should be a **deployment slot setting** pinned to the slot.
4. Save, review the restart notice, and verify app health after the change.
5. Monitor Log stream, health endpoints, and HTTP metrics.

### In the CLI

~~~bash
RG="<RESOURCE_GROUP>"
APP="<WEB_APP_NAME>"

az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --settings APP_ENV=production LOG_LEVEL=info FEATURE_EXPORT_ENABLED=false
~~~

List only setting **names** to avoid accidentally printing sensitive values:

~~~bash
az webapp config appsettings list \
  --resource-group "$RG" \
  --name "$APP" \
  --query "[].{name:name,slotSetting:slotSetting}" \
  --output table
~~~

The following command **deletes** an app setting; run it only if you know the code no longer needs it:

~~~bash
az webapp config appsettings delete \
  --resource-group "$RG" \
  --name "$APP" \
  --setting-names FEATURE_EXPORT_ENABLED
~~~

Never pass real passwords or connection strings via **--settings SECRET=value** in a shared terminal: they can end up in shell history, pipeline logs, or command traces. Use Key Vault references or an organization-approved secret mechanism.

### How are Connection strings different?

The Portal also includes a **Connection strings** section to store connection settings by type and surface them to the runtime in a platform-specific way. On some Windows/.NET stacks, they have specific prefixes or framework integrations. For modern apps, **App settings + Key Vault references** often yield a more uniform and manageable pattern; choose based on your framework and existing requirements.

Do not assume every connection string created in the Portal appears in your app under the exact variable name you typed. Verify runtime mapping and how your client SDK reads configuration.

## 8. Protecting secrets with Managed Identity and Key Vault references

Database passwords, API keys, or access tokens should never be committed to a repository, written into a Dockerfile, or exposed in deployment pipelines. App Service supports **managed identities** and **Azure Key Vault references** so apps consume secrets in a managed way.

### Conceptual flow

~~~text
Web App
  |
  +-- Managed identity (Entra ID)
  |        |
  |        v
  |   Key Vault (secret read permission granted)
  |        |
  +-- App setting:
       DB_PASSWORD = @Microsoft.KeyVault(SecretUri=...)
           |
           v
     App Service resolves secret
           |
           v
     Application process reads DB_PASSWORD
~~~

The application still reads **DB_PASSWORD** normally, but in App Service configuration you store a **Key Vault reference** instead of copying the secret value into deployment configs.

Example reference syntax:

~~~text
@Microsoft.KeyVault(SecretUri=https://<VAULT_NAME>.vault.azure.net/secrets/<SECRET_NAME>/)
~~~

This is an illustrative template—replace with your real vault and secret in a managed environment. You can specify a concrete secret version when pinning is required, or omit the version where supported to pick up the current version via the platform's refresh/cache mechanism.

### Preparation steps

1. Enable a **system-assigned** or configure a **user-assigned managed identity** on the Web App per your design.
2. In Key Vault, grant **secret read** permission to that identity: e.g., the **Key Vault Secrets User** role when the vault uses Azure RBAC, or a **Get** access policy if using vault access policies.
3. If Key Vault allows private network access only, configure App Service VNet integration, private endpoints, DNS/routing, and supported vault access settings.
4. Create an App setting holding the reference, not a plaintext password.
5. Check **Key Vault reference status** in the Portal and confirm the application connects successfully.
6. Plan for rotation and refresh; do not assume every app picks up rotated secrets instantaneously in all cases.

CLI example enabling system-assigned identity:

~~~bash
az webapp identity assign \
  --resource-group "$RG" \
  --name "$APP"
~~~

Example setting a reference instead of a direct secret:

~~~bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --settings 'DB_PASSWORD=@Microsoft.KeyVault(SecretUri=https://<VAULT_NAME>.vault.azure.net/secrets/<SECRET_NAME>/)'
~~~

The syntax uses **single quotes in Bash** so the shell does not interpret the string. Replace placeholders and verify subscription, Key Vault permissions, and the source secret. The command above **does not automatically grant Key Vault read permissions** and does not create the secret itself.

### Common Key Vault reference errors

| Symptom | Possible cause | How to check |
|---|---|---|
| App sees literal **@Microsoft.KeyVault(...)** instead of secret | Reference failed to resolve | Check syntax, identity, vault permissions, reference status |
| 403 error to Key Vault | Managed identity lacks permission or wrong principal | Check RBAC/access policy and Web App identity |
| Timeout fetching secret | Private Endpoint, DNS, VNet integration, firewall, or route | Check network path and name resolution |
| Secret rotated but app still uses old value | Platform or application caching/refresh | Check refresh cycle, appropriate restart/setting change, and in-app cache |

**Key Vault references involve caching/refreshing**, and app configuration updates can trigger refreshes. Do not consider secret rotation complete until you verify the live version/value **without printing secrets to logs** and confirm connectivity works.

## 9. What is a startup command?

After receiving the artifact and preparing the runtime, App Service needs to know **which process will serve HTTP requests**. Some runtimes auto-detect the project and run a default command; for custom apps, you must specify a **Startup Command** (represented on many Linux Web Apps as **appCommandLine**).

Example:

~~~text
App Service Linux code-based
    |
    +-- Runtime stack: Python
    +-- Deployment artifact: source + dependencies
    +-- Startup command: gunicorn --bind=0.0.0.0:8000 app:app
    |
    v
gunicorn process runs, binds the platform-routed port
    |
    v
Health checks / HTTP requests
~~~

**A startup command is not a build command.** Commands like **npm install**, **pip install**, **dotnet publish**, or compilation belong in the build/deploy phase; you normally should not re-run a full build every time a container/instance boots.

### Elements that must be right

1. **Executable exists:** `node`, `npm`, `gunicorn`, `java`, or your app's executable.
2. **Correct working directory:** the file you invoke actually exists in the package/deployment path.
3. **Dependencies installed:** `node_modules`, Python packages, matching framework runtime.
4. **Listening on the right network interface and port:** usually **0.0.0.0**, not only **127.0.0.1** in container/network topologies that receive platform-forwarded traffic.
5. **Process stays alive:** must not run and exit if it is the web-serving process.
6. **Logs to stdout/stderr** as appropriate so Azure can capture diagnostics.
7. **Shutdown/restart:** the application handles termination signals and closes connections gracefully where supported by the framework.

An incorrect startup command can leave the App Service site resource showing Running while the application is unable to accept requests.

## 10. Default startup and Node.js applications

For code-based Node.js on Linux, App Service detects how to launch the app and can rely on **package.json/start script** or a configured command per runtime behavior. Do not assume a TypeScript file runs directly without being compiled to JavaScript first.

Minimal HTTP app example:

~~~javascript
// server.js
const http = require("http");

const port = Number(process.env.PORT || 8080);
const host = "0.0.0.0";
const env = process.env.APP_ENV || "development";

const server = http.createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok" }));
    return;
  }

  res.writeHead(200, { "Content-Type": "text/plain; charset=utf-8" });
  res.end("App running in " + env);
});

server.listen(port, host, () => {
  console.log("HTTP server listening on " + host + ":" + port);
});
~~~

A valid **package.json** with a start script:

~~~json
{
  "name": "app-service-runtime-demo",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "start": "node server.js"
  }
}
~~~

If an explicit startup command is needed:

~~~text
npm start
~~~

The app reads **process.env.PORT** when provided by the platform, has a fallback for local runs, and binds to **0.0.0.0**. For real apps/frameworks, verify which port App Service routes for your chosen stack instead of hard-coding an assumed port.

### Common Node.js errors

| Error | Cause | Check |
|---|---|---|
| **Cannot find module** | Missing dependency or missing build output | Artifact, npm install/build logs, package.json |
| **npm ERR! Missing script: start** | No start script while startup invokes `npm start` | Add a valid start script or set the right command |
| **EADDRINUSE** | Two processes listening on the same port | Check startup for duplicate process launches |
| App binds only **127.0.0.1** | Platform cannot reach the process over the topology | Bind the documented host/port |
| Boots locally but missing config in Azure | `APP_ENV` or other variables not supplied | Verify app settings and exact names |

## 11. Startup commands for Python and WSGI/ASGI frameworks

On code-based Linux Python App Service, the platform can auto-detect common projects and launch an appropriate server. However, not every repository layout is auto-detected accurately.

Example Flask project:

~~~text
app.py
requirements.txt
~~~

**app.py:**

~~~python
from flask import Flask, jsonify
import os

app = Flask(__name__)

@app.get("/health")
def health():
    return jsonify(status="ok", app_env=os.getenv("APP_ENV", "development"))
~~~

**requirements.txt:**

~~~text
Flask
gunicorn
~~~

Example startup command:

~~~bash
gunicorn --bind=0.0.0.0:8000 --timeout 600 app:app
~~~

In **app:app**, the first part is the Python module **app.py**, and the second part is the Flask object **app**. If your repository puts it in a subfolder, update the module path/working directory accordingly. This command only works if **gunicorn is installed** in the app environment and the build brought all dependencies.

### Django

Django typically uses a WSGI entrypoint like:

~~~text
gunicorn --bind=0.0.0.0:8000 myproject.wsgi:application
~~~

Replace **myproject** with your real Django package name. Configure **ALLOWED_HOSTS**, static files, database migrations, and framework settings. Running the development server **manage.py runserver** is not a standard production option just because it works on a laptop.

### ASGI (FastAPI, Django ASGI)

ASGI requires an ASGI-capable server/worker, such as properly configured Uvicorn/Gunicorn workers. Do not mechanically reuse the WSGI **app:app** command above for every FastAPI app. Check framework documentation and exact server versions.

### Common Python errors

- **ModuleNotFoundError:** dependencies were not installed in the deployment environment, or the module path is wrong.
- **gunicorn: command not found:** `gunicorn` is missing from dependencies or the environment was not built properly.
- **Error loading ASGI/WSGI app:** wrong module path, app object name, or an import-time exception.
- **Missing migrations:** the app boots but database queries fail; run migrations separately from request serving.
- **Static files not appearing:** missing collect/build step or static serving configuration.

With Python, clearly distinguish **Oryx/build automation** from the **startup command**. Install dependencies during deployment instead of trying to install them on every instance boot.

## 12. .NET, Java, and Linux/Windows differences

### .NET

ASP.NET Core apps on App Service can use built-in runtimes when targeting a supported framework. On Windows, hosting typically ties into **IIS/ASP.NET Core Module** depending on the model; on Linux, the app runs inside the runtime stack's Linux environment. Startup behavior differs between the two OSes.

For .NET, a **manual startup command is usually unnecessary** if you publish artifacts as expected by the platform and use a compatible runtime. Before manually adding **dotnet MyApp.dll**, check deployment type, working directory, publish output, and App Service documentation.

### Java

App Service supports Java models such as **Java SE** and **Tomcat** depending on the offered stack. A self-contained JAR (such as Spring Boot) does not have the same deployment layout as a WAR for Tomcat. Pick the matching runtime/Java version and deployment method; do not mix **java -jar** commands with Tomcat WARs without an architectural reason.

Some frameworks use environment variables such as **SPRING_PROFILES_ACTIVE** or **JAVA_TOOL_OPTIONS**, but set them based on actual app requirements and runtime guidance; avoid excessive JVM flags without measuring memory/performance.

### Windows vs. Linux

| Topic | App Service Linux | App Service Windows |
|---|---|---|
| Startup command | Explicit Startup Command supported for many built-in stacks | Typically relies on Windows/IIS hosting or appropriate entrypoint |
| Shell/scripts | Bash/sh and Unix paths | PowerShell/cmd, Windows paths depending on model |
| Case sensitivity | Files and environment variables are typically case-sensitive | Behavior varies by system/framework |
| Runtime setting | Often uses `linuxFxVersion` for code-based stacks | Windows-specific stack/version configuration |
| Custom container | Linux Docker image | Check Windows Container model and current support |

Do not copy a Linux startup command with **/** paths, **bash** commands, or WSGI modules onto a Windows Web App and conclude App Service is broken. On Windows, investigate `web.config`, IIS/hosting modules, and deployment artifacts for the selected stack.

## 13. Setting the startup command via Portal and CLI

### Portal

1. Open the code-based Linux Web App.
2. Select **Configuration/General settings** or the corresponding startup configuration page.
3. Enter **Startup Command** if the default mechanism cannot detect the entrypoint.
4. Save, observe the restart, inspect Log stream, and verify the health endpoint.

### CLI

~~~bash
az webapp config set \
  --resource-group "$RG" \
  --name "$APP" \
  --startup-file "npm start"
~~~

For a Python Flask app with **app.py** in the expected location and `gunicorn` installed:

~~~bash
az webapp config set \
  --resource-group "$RG" \
  --name "$APP" \
  --startup-file "gunicorn --bind=0.0.0.0:8000 app:app"
~~~

**Do not run both commands above on the same app**: they are two independent examples for two different runtimes. Each update changes configuration and can trigger a restart; apply only the command matching your assigned app.

Inspect the current command:

~~~bash
az webapp config show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{startup:appCommandLine,runtime:linuxFxVersion}" \
  --output json
~~~

**Startup file/script:** if using a script like **startup.sh**, ensure it is deployed with the expected path and executable permissions. Do not assume the script exists under **/home/site/wwwroot** if your deployment pipeline places artifacts elsewhere or mounts a read-only package. Startup script placement/execution depends on deployment mode.

## 14. HTTP ports and bind addresses: built-in runtime vs. custom container

An application process can run without serving requests if it listens on the wrong port. This is one of the most common App Service deployment mistakes.

### Built-in Linux runtime

With built-in stacks, the platform typically supplies port/startup configuration matching the runtime. Your code must use the port provided by the environment or the server command documented for that runtime. For example, Node.js typically reads **process.env.PORT**; Python Gunicorn examples in App Service Linux docs typically bind **0.0.0.0:8000**.

Do not treat **8000** or **8080** as a universal fixed port for every Web App: frameworks, stacks, and launch mechanisms differ.

### Custom Linux container

With a custom container, the app must listen on the port App Service routes traffic to. App Service supports the **WEBSITES_PORT** setting to specify the **application container port** in supported configurations (often defaulting to port 80 when unspecified).

Example container running an app on port 8080:

~~~dockerfile
FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
EXPOSE 8080
CMD ["node", "server.js"]
~~~

Corresponding App Service setting:

~~~text
WEBSITES_PORT=8080
~~~

Inside the container, the process must **actually listen on 0.0.0.0:8080**. A Dockerfile **EXPOSE 8080** only documents port intent; it does not force the process to bind that port. **WEBSITES_PORT** tells App Service which container port to route to, and is not necessarily automatically passed inside the image as the **PORT** environment variable; if your code reads `PORT`, align the image's runtime configuration.

**Do not treat WEBSITES_PORT as a universal fix-all** for built-in runtimes. When unsure about ports, inspect container/startup logs and docs for that exact Web App type.

### Apps must listen on 0.0.0.0 when required

~~~text
Listen only on 127.0.0.1:8080
  -> requests from reverse proxy/container networking may fail to reach it

Listen on 0.0.0.0:8080
  -> process accepts requests on the interface configured by the environment
~~~

You must still enforce security controls at App Service/network/identity layers; binding **0.0.0.0** inside the container does not mean exposing an unauthenticated public API.

## 15. Build, deployment, and startup are three separate phases

When a Web App fails to run, identify **which phase failed**:

| Phase | Actions | Failure symptoms |
|---|---|---|
| **Build** | Install dependencies, compile, generate static assets, run checks | npm/pip/dotnet build fails, incompatible packages |
| **Deployment** | Push artifact/image to App Service, mount/package, apply config | Wrong ZIP path, missing files, container pull failure |
| **Startup** | Select runtime, launch entrypoint, bind port, initialize service | ModuleNotFoundError, missing secret, process exits, ping timeout |
| **Runtime** | Serve HTTP requests and call dependencies | HTTP 5xx, DB timeouts, auth errors, memory pressure |

### Oryx and remote builds on Linux

Some code-based Linux stacks use **Oryx** to detect the language, install dependencies, and generate startup commands based on deployment settings. However, not every deployment automatically triggers a remote build. Settings such as **SCM_DO_BUILD_DURING_DEPLOYMENT** or related build flags should only be enabled when aligned with your deployment method and runtime documentation.

If you deploy a pre-built artifact, do not assume App Service will re-run **npm install** or **pip install**. If you deploy raw source code, do not assume dependencies already exist in the container before the build pipeline runs.

### Run from package

Some deployment methods use **WEBSITE_RUN_FROM_PACKAGE** to mount a package, typically making **wwwroot read-only** in that supported model. Do not write startup scripts that try to write build artifacts or install packages directly into a read-only application directory.

Separate temporary and persistent data from the source folder; for user uploads, prefer Blob Storage or an appropriate managed storage service. Do not rely on the App Service local filesystem as a shared database across instances.

## 16. Deployment slots and slot settings

**Deployment slots** let you validate a release on a separate URL/slot before shifting traffic. They have their own configuration and swap behavior per tier support.

Example:

~~~text
Web App: orders-api
  |
  +-- production slot
  |      APP_ENV=production
  |      DB_ENDPOINT=database-production
  |
  +-- staging slot
         APP_ENV=staging
         DB_ENDPOINT=database-staging
~~~

The goal is for staging to test a new release **without accidentally writing to the production database**. Therefore, environment-sensitive settings such as DB endpoints, secret references, callback URLs, or certain feature flags should usually be marked as **deployment slot settings (sticky)** if the swap workflow requires it.

### What are sticky settings?

Settings marked as a **deployment slot setting** stay pinned to their slot during a swap according to App Service rules. Not all App Service settings swap identically; verify the reference table of which settings swap and which stay sticky.

Example setting a slot-specific value for staging:

~~~bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --slot staging \
  --slot-settings APP_ENV=staging
~~~

This command requires the **staging** slot to already exist; **it does not create the slot**. Slot deployment availability depends on the App Service Plan tier; slots carry tier limits/costs and share the plan's compute capacity. When using slots to test configuration:

1. Ensure settings that must stay sticky are properly marked.
2. Isolate staging secrets and databases from production.
3. Verify the startup command/runtime on the target slot.
4. Run smoke tests before swapping.
5. Have a rollback plan and monitor logs/metrics after swapping.

**Swapping does not replace database migration planning.** If the new release ran an incompatible migration, swapping back to the old artifact may not restore the data cleanly.

## 17. Always On, health checks, and availability

App Service offers an **Always On** option on supported tiers to keep the application active instead of letting it go idle as on lower tiers. This helps apps needing consistent response latency, certain background tasks, and warm-up.

However, **Always On does not guarantee zero downtime**: configuration changes, deployments, scaling, runtime errors, or backend dependency outages can still cause disruption. Nor is this option a substitute for a reliable queue/worker system for long-running jobs.

### Health checks

Design a simple endpoint:

~~~text
GET /health
200 OK           -> instance/app can serve per defined criteria
503 Unavailable  -> instance is not ready yet
~~~

If you enable App Service's **Health check** feature, configure the right path and ensure the endpoint is reachable by the platform per service rules. The endpoint should return success **when the instance is truly ready**, avoiding unconditionally returning 200 when the app lacks connectivity to mandatory components.

At the same time, avoid overly deep health checks: if a non-critical secondary service blips, do not immediately mark every instance unhealthy. Distinguish **liveness**, **readiness**, and business dependency status.

**Security:** health endpoints must not expose connection strings, secrets, stack traces, or sensitive system info. Use Application Insights/monitoring to collect details through controlled channels.

## 18. Diagnosing startup errors in App Service

An effective sequence:

1. **Verify the Web App resource:** right subscription, resource group, OS, plan, state, and deployment slot.
2. **Verify the runtime:** do the stack configuration and version match the artifact/framework?
3. **Verify the artifact:** do the entrypoint file, build output, and dependencies exist at the path App Service actually executes?
4. **Verify the startup command:** is the command valid, does the executable/module exist, and does it bind the right port?
5. **Verify app settings:** names, formats, secret references, slot stickiness, and dependency permissions.
6. **Inspect logs:** deployment/build logs, Log stream, app/container startup logs, Application Insights.
7. **Check networking:** database/Key Vault/DNS/private endpoints/egress/firewalls if startup depends on them.
8. **Make one narrow change**, re-verify with health/smoke tests, and keep a rollback path ready.

### Enabling and reading logs

In the Portal, open **Monitoring > App Service logs** or the corresponding logging page, configure logging appropriate for your runtime and data policies, and use **Log stream** to view output. With Azure CLI:

~~~bash
az webapp log tail \
  --resource-group "$RG" \
  --name "$APP"
~~~

This command streams logs interactively; press **Ctrl+C** to stop. If no data appears, verify the app type, whether logging is enabled, whether stdout/stderr are written, and whether log tail is supported in your deployment model.

You can also use **Diagnose and solve problems** in App Service, deployment logs, and tools like **Kudu/Advanced Tools or SSH console** depending on OS and Web App type. Not all Kudu/SSH features behave identically across custom containers, code-based Linux, and Windows.

### Common error matrix

| Symptom | Possible cause | How to verify |
|---|---|---|
| App returns **Application Error** after deploy | Process failed to start, exited early, or import-time exception | Startup/container logs and runtime |
| **ModuleNotFoundError / Cannot find module** | Missing build/dependency, wrong module path | Manifest, artifact, build logs |
| **gunicorn: command not found** | Missing dependency or build skipped | `requirements.txt` and deploy output |
| **npm start** fails | `package.json` missing `start` script, wrong folder | `package.json` scripts and `appCommandLine` |
| Container hits **HTTP ping timeout** | Wrong port, bound localhost, slow boot, or process exit | Logs, `WEBSITES_PORT`, Docker `CMD`/`ENTRYPOINT` |
| **Key Vault reference** fails to resolve | Identity lacks permission, bad reference, or network unreachable | Reference status, managed identity, vault permissions |
| App works in staging but fails in production | Sticky settings/swap mismatch, different secrets or dependencies | Compare slot settings without exposing secrets |
| HTTP **500** after startup | Code bug or runtime dependency error | App logs, tracing, Application Insights |
| HTTP **502/503** | Unhealthy app, instance/port/startup/backend issue | Health/instance metrics, platform diagnostics |
| App restarts on settings change and drops sessions | Configuration recycle, session stored on instance | Shared session store or stateless architecture |
| App fails to boot after runtime change | Binary/dependency incompatible with version | Roll back runtime after checking; test in staging |
| File uploads fail or data is inconsistent | Relying on local/read-only filesystem or wrong storage path | Deployment mode, persistent storage, and Blob Storage |

**An HTTP status code alone does not reveal a single root cause.** For example, 503 can happen because the app is not listening on the right port, instances were marked unhealthy, or other conditions. Base conclusions on logs and actual resource state.

## 19. Security and configuration governance

Runtimes and app settings are part of the attack surface:

- **Never commit secrets** into Git, `package.json`, Dockerfiles, config files, or READMEs.
- **Restrict RBAC:** someone permitted to edit App settings or startup commands can alter app behavior and potentially cause the app to read or exfiltrate sensitive data. Grant only appropriate roles.
- **Use managed identities and Key Vault** for supported resources instead of long-lived credentials in code.
- **Separate environments** (dev/staging/prod) and slot settings so staging never writes to production.
- **Never dump all environment variables to logs** for debugging; they may contain secrets and connection strings.
- **Restrict network access** to databases and Key Vault per policy; if using VNet/private endpoints, configure DNS/routes and egress properly.
- **Audit changes** via Azure Activity Log, deployment audits, and IaC reviews.
- **Manage runtime lifecycles:** update to security-supported versions, test dependencies, and plan rollbacks.
- **Enforce TLS** on public endpoints and downstream connections as appropriate.

Just because a secret setting is masked in the Portal does not mean anyone with app-management permissions cannot affect how that secret is used. Combine least privilege, auditing, approvals, and separated environments.

## 20. Configuration with Infrastructure as Code and CI/CD

To avoid drift, declare runtime versions, **App setting names**, slot stickiness, and startup commands in IaC tools such as **Bicep/Terraform** following organizational standards. Secret values should be **referenced** rather than written inline in templates or exposed pipeline variables.

Example **conceptual configuration template** (not valid Bicep/Terraform to run directly):

~~~yaml
webApp:
  operatingSystem: Linux
  runtimeStack: "<RUNTIME_FROM_SUPPORTED_LIST>"
  startupCommand: "npm start"
  settings:
    APP_ENV: production
    LOG_LEVEL: info
    DB_PASSWORD: "@Microsoft.KeyVault(SecretUri=https://<VAULT>/secrets/<NAME>/)"
  deploymentSlotSettings:
    - APP_ENV
    - DB_PASSWORD
~~~

The pipeline should:

1. Validate source/dependencies and build an artifact matching the target runtime.
2. Verify target environment, App Service Plan/OS, and Runtime Stack compatibility.
3. Deploy to staging first when supported and required by the workload.
4. Apply configuration from IaC/pipeline safely without logging secret values.
5. Run health/smoke tests (covering app endpoints and required dependencies).
6. Promote/swap or execute a controlled rollout while monitoring error rates/latency.
7. Maintain rollback paths for **artifacts**, **runtime versions**, and **settings**.

**Be careful when rolling back:** a migrated database schema may be incompatible with an older application version. Do not treat swapping the app or reverting the runtime as a guaranteed recovery path for every change.

## 21. Hands-on: configuring a Linux Web App in a sandbox

Goal: inspect the runtime, add non-sensitive environment variables, set a startup command matching the deployed artifact, read back configuration, and verify HTTP responses. You can run this on an **existing lab Web App** or create a dedicated plan/app if budget approval is granted.

### Option A — using an existing lab Web App

Preparation:

- Granted management permissions on a test Web App (not production).
- Know the language/runtime and actual startup file of the app.
- Have Azure CLI, the right subscription, and permissions to edit the Web App.
- Have access to view logs or Application Insights if needed.

#### Step 1: inspect configuration

~~~bash
az login
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

RG="<LAB_RESOURCE_GROUP>"
APP="<LAB_WEB_APP_NAME>"

az webapp show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{name:name,state:state,kind:kind,url:defaultHostName}" \
  --output json

az webapp config show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{runtime:linuxFxVersion,startup:appCommandLine,alwaysOn:alwaysOn}" \
  --output json
~~~

#### Step 2: add non-sensitive settings

~~~bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$APP" \
  --settings APP_ENV=lab LOG_LEVEL=info
~~~

List setting names without printing values:

~~~bash
az webapp config appsettings list \
  --resource-group "$RG" \
  --name "$APP" \
  --query "[].name" \
  --output table
~~~

#### Step 3: set startup command matching the app in use

**Only for a deployed Node.js app that has a start script:**

~~~bash
az webapp config set \
  --resource-group "$RG" \
  --name "$APP" \
  --startup-file "npm start"
~~~

**If the app is not Node.js**, do not run the command above. Substitute a verified startup command for your framework, or leave the default startup behavior if appropriate. Every update can restart the app.

#### Step 4: verify

~~~bash
az webapp config show \
  --resource-group "$RG" \
  --name "$APP" \
  --query "{runtime:linuxFxVersion,startup:appCommandLine}" \
  --output json

az webapp log tail \
  --resource-group "$RG" \
  --name "$APP"
~~~

Using the hostname returned by App Service, test **GET /health** or whichever endpoint your app supports. Do not treat **/health** as mandatory proof if your app does not implement that route.

#### Step 5: clean up changes

If using a **pre-existing** lab app, revert the startup command and `APP_ENV`/`LOG_LEVEL` back to their **pre-lab values** from your baseline record. **Do not delete an entire Web App or resource group managed by someone else.**

### Option B — creating a new lab Web App (optional)

If permitted to create billable resources, here is a CLI pattern for a Linux App Service Plan:

~~~bash
RG="rg-appservice-runtime-lab"
LOCATION="southeastasia"
PLAN="asp-runtime-lab"
APP="<GLOBALLY_UNIQUE_LAB_APP_NAME>"
RUNTIME="<SUPPORTED_LINUX_RUNTIME_VALUE>"

az group create \
  --name "$RG" \
  --location "$LOCATION"

az appservice plan create \
  --resource-group "$RG" \
  --name "$PLAN" \
  --location "$LOCATION" \
  --is-linux \
  --sku B1

az webapp list-runtimes --os-type linux --output table

az webapp create \
  --resource-group "$RG" \
  --plan "$PLAN" \
  --name "$APP" \
  --runtime "$RUNTIME"
~~~

Before running: replace placeholders, choose a truly supported runtime, check quotas, and **verify B1 plan pricing** in your region. The Web App name must be valid and unique in the endpoint namespace. This sequence **has not deployed code yet**, so creating the app does not prove the startup command can run a real server.

After deploying a test app matching the runtime and verifying health, clean up the entire resource group only if **you created it yourself and it contains no other resources**:

~~~bash
az group delete --name "$RG" --yes
az group exists --name "$RG"
~~~

Never delete a shared or production resource group. Check Azure Cost Management since billing data can lag; stopping a Web App does not necessarily stop App Service Plan charges.

## 22. Case study: Python API fails to start

A development team deploys a Flask API to **Linux App Service**. Their source file is **src/api.py**, defining **app = Flask(__name__)**. Logs report:

~~~text
ModuleNotFoundError: No module named 'app'
gunicorn: command not found
~~~

Configuration details:

~~~text
Runtime: Python (an App Service supported version)
Startup Command: gunicorn app:app
Artifact:
  requirements.txt
  src/api.py
~~~

### Analysis

There are **at least two potentially independent issues**:

1. The module path in the startup command **app:app** does not match **src/api.py**.
2. **gunicorn** is not found: `requirements.txt` may lack `gunicorn`, or the build/deploy step did not install dependencies.

Do not simply switch to a newer Python runtime and assume the problem is solved. Inspect artifact paths, dependencies, build logs, working directory, and the package structure of **src**.

### Remediation

- Ensure **requirements.txt** includes appropriate **Flask** and **gunicorn** entries.
- Determine the module import path from the working directory: for example **src.api:app** if **src** is importable and package structure/`PYTHONPATH` align; or configure startup to run from the proper directory.
- Enable/verify appropriate build automation so dependencies are actually installed.
- Confirm Gunicorn binds the proper interface/port in App Service Linux.
- Deploy to lab/staging and inspect logs after restart rather than editing production directly.

### Completion criteria

| Check | Expected outcome |
|---|---|
| Build logs | Dependencies install cleanly |
| Startup logs | No more ModuleNotFoundError or missing gunicorn |
| Runtime | Matches the artifact's Python version |
| App settings | `APP_ENV`/secret references configured accurately |
| GET /health | Returns success status |
| Business API | Connects to database and handles real requests properly |

## 23. Case study: custom container listens on the wrong port

Another team packages a Node.js app as a container, with code hard-coding **listen(3000, "127.0.0.1")**. They set App Service **WEBSITES_PORT=8080**. The container starts, yet App Service reports timeouts.

### Why does it fail?

- The platform is trying to route traffic to port **8080**, while the app runs on port **3000**.
- The app binds only **127.0.0.1**, so it may not accept connections arriving over the platform's container networking path.
- Neither Dockerfile **EXPOSE** nor an app setting rewrites **server.listen()** in code.

### Resolution

1. Pick one port for the app to actually listen on (e.g., 8080).
2. Update code or startup configuration to bind **0.0.0.0:8080**.
3. Set **WEBSITES_PORT=8080** for the custom container where required by the model.
4. Build and push the new image; deploy to lab/staging.
5. Check container startup logs, health, and HTTP endpoints; confirm timeouts are gone.

Do not change ports randomly in production without knowing the app/framework and container runtime behavior. Some containers already honor `PORT` or image defaults; align every layer consistently.

## 24. Production readiness checklist

- [ ] Runtime/OS/App Service Plan match the app and supported version lifecycle.
- [ ] Build pipeline, artifact, and runtime use compatible versions/dependencies.
- [ ] Startup command is set only when needed, with accurate executable, module path, working directory, and persistent process.
- [ ] App binds the right interface/port for built-in runtime or custom container; `WEBSITES_PORT` is not confused with `PORT`.
- [ ] App settings are named consistently; booleans/numbers are parsed and validated.
- [ ] No hard-coded secrets; Key Vault references/managed identities have proper permissions and verified resolution status.
- [ ] Connection strings, VNet integration, Private Endpoints, DNS, and outbound access have been tested.
- [ ] Slot settings are properly marked; staging never writes to production data.
- [ ] Changes to app settings/runtime/startup include restart, warm-up, and rollback plans.
- [ ] Log stream, Application Insights, health endpoints, and error alerts are active.
- [ ] Instance local filesystem is not relied upon for irreplaceable business data.
- [ ] IaC/CI/CD manage configuration, changes are reviewed beforehand, and audit trails are kept.
- [ ] Smoke tests, HTTP 5xx handling, startup time, and scaling behavior have been tested.
- [ ] Tier, Always On/slots, and costs for App Service Plan, logging, and networking have been reviewed.

## 25. Self-check questions

1. How does an App Service Plan differ from a Web App? Can two Web Apps sharing a plan affect each other's performance?
2. On code-based Linux, how does the runtime stack differ from the Node/Python version installed inside a custom container image?
3. Why can updating App settings trigger a restart and disrupt active sessions?
4. Does **APP_ENV=production** automatically make Azure switch runtimes or enforce HTTPS?
5. How are environment variables read in Node.js, Python, .NET, and Java?
6. Why shouldn't real passwords be passed via **--settings DB_PASSWORD=...** in a terminal or pipeline?
7. What elements are needed for a Key Vault reference to resolve successfully?
8. How does a startup command differ from a build command and a deployment command?
9. Why does a Python App Service app need `gunicorn` and a module path matching the artifact?
10. In a custom container, does **WEBSITES_PORT** automatically force the program to listen on that port?
11. On Windows App Service, why shouldn't you copy a Linux Bash startup command?
12. What risk do slot settings address during a staging ↔ production swap?
13. When App Service reports Application Error, which data should you inspect before changing the runtime?
14. Does Always On guarantee zero HTTP 5xx errors or zero cold starts in every situation?
15. Why does a successful pipeline deployment not prove the application is serving requests properly?

## 26. References

- [Configure an App Service app](https://learn.microsoft.com/azure/app-service/configure-common) — Application settings, general settings, startup, and common options.
- [Configure a Linux App Service app](https://learn.microsoft.com/azure/app-service/configure-linux-open-ssh-session) — accessing and operating Linux apps, SSH under supported models.
- [Configure Node.js applications in Azure App Service](https://learn.microsoft.com/azure/app-service/configure-language-nodejs) — runtime, dependencies, and startup.
- [Configure Python applications in Azure App Service](https://learn.microsoft.com/azure/app-service/configure-language-python) — Oryx, Gunicorn, Flask/Django, and startup.
- [Configure .NET applications in Azure App Service](https://learn.microsoft.com/azure/app-service/configure-language-dotnetcore) — .NET hosting and runtime.
- [Configure Java applications in Azure App Service](https://learn.microsoft.com/azure/app-service/configure-language-java) — Java SE/Tomcat and configuration.
- [Configure a custom container for Azure App Service](https://learn.microsoft.com/azure/app-service/configure-custom-container) — image, port, and container variables.
- [Key Vault references for Azure App Service](https://learn.microsoft.com/azure/app-service/app-service-key-vault-references) — managing secrets via managed identity and references.
- [Set up staging environments with deployment slots](https://learn.microsoft.com/azure/app-service/deploy-staging-slots) — slot settings and swaps.
- [Enable diagnostic logging for Azure App Service](https://learn.microsoft.com/azure/app-service/troubleshoot-diagnostic-logs) — logging for deployment/startup failures.
- [Azure CLI: az webapp config](https://learn.microsoft.com/cli/azure/webapp/config) — runtime and startup command.
- [Azure CLI: az webapp config appsettings](https://learn.microsoft.com/cli/azure/webapp/config/appsettings) — create, read, and delete app settings.

**Conclusion:** To run applications reliably on Azure App Service, align the **runtime stack**, **build artifact**, **application settings**, and **startup command**. Sensible defaults do not fit every case: check supported runtime versions, specify the exact entrypoint/port, use Key Vault and managed identities for secrets, validate on staging, and monitor logs and health after every change. Controlled configuration cuts deployment failures, protects data, and avoids wasted operational spend.
